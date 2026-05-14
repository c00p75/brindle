"""Balance snapshot persistence + analytics queries.

Append-only series of broker balance observations. Powers:
  - Live equity curve (real broker balance, not synthetic position math)
  - Drawdown / high-water-mark tracking
  - "What was my balance on date X" lookups
  - Time-bucketed aggregates for analytics dashboards

Throttling: callers should already throttle (the runtime polls every ~30s).
We don't dedupe identical balances — repeated identical rows are cheap and
preserve the "we observed this at time T" record.
"""
from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from app.core.ids import new_id
from app.core.time import now_epoch_ms
from app.db.engine import session_scope
from app.db.orm import BalanceSnapshotRow

log = logging.getLogger("balance_history")


def record(*, bot_id: str, balance: float, currency: str, source: str = "poll",
           at_ms: int | None = None) -> None:
    """Persist one balance observation. Idempotent only insofar as duplicates
    are tolerated — call sites are expected to throttle."""
    with session_scope() as s:
        s.add(BalanceSnapshotRow(
            id=new_id("bs"),
            bot_id=bot_id,
            balance=balance,
            currency=currency,
            at_ms=at_ms if at_ms is not None else now_epoch_ms(),
            source=source,
        ))
        s.flush()


def history(*, bot_id: str, since_ms: int | None = None, until_ms: int | None = None,
            max_points: int = 1000) -> list[dict[str, Any]]:
    """Return balance series in [since_ms, until_ms] in chronological order.

    Downsamples to at most `max_points` entries via stride sampling — enough
    detail for charts without dragging huge arrays through JSON.
    """
    with session_scope() as s:
        q = sa.select(BalanceSnapshotRow).where(BalanceSnapshotRow.bot_id == bot_id)
        if since_ms is not None:
            q = q.where(BalanceSnapshotRow.at_ms >= since_ms)
        if until_ms is not None:
            q = q.where(BalanceSnapshotRow.at_ms <= until_ms)
        q = q.order_by(BalanceSnapshotRow.at_ms.asc())
        rows = s.execute(q).scalars().all()

    if not rows:
        return []
    if len(rows) <= max_points:
        return [_row_dict(r) for r in rows]
    # Stride-sample but always include first and last for accurate endpoints.
    stride = max(1, len(rows) // max_points)
    sampled = rows[::stride]
    if rows[-1].id != sampled[-1].id:
        sampled.append(rows[-1])
    return [_row_dict(r) for r in sampled]


def latest(bot_id: str) -> dict[str, Any] | None:
    with session_scope() as s:
        row = s.execute(
            sa.select(BalanceSnapshotRow)
            .where(BalanceSnapshotRow.bot_id == bot_id)
            .order_by(BalanceSnapshotRow.at_ms.desc())
            .limit(1)
        ).scalar_one_or_none()
    return _row_dict(row) if row else None


_BUCKET_MS = {"minute": 60_000, "hour": 3_600_000, "day": 86_400_000}


def analytics(*, bot_id: str, since_ms: int, until_ms: int,
              granularity: str = "hour") -> list[dict[str, Any]]:
    """Time-bucketed performance metrics for a bot.

    Each bucket aggregates two independent data sources:
      - Contracts purchased in the bucket (counts, stakes, win/loss, contract P&L)
      - Balance snapshots in the bucket (open/close/min/max — the real equity curve)

    Granularity: 'minute' | 'hour' | 'day'. Unknown values are coerced to 'hour'.
    Returns buckets sorted ascending. Buckets where NEITHER source had data are
    omitted to keep payloads small; partial buckets (only contracts, only
    balance) ARE included with the missing fields as null.
    """
    from app.db.orm import ContractRow

    bucket_size = _BUCKET_MS.get(granularity, _BUCKET_MS["hour"])
    if since_ms >= until_ms:
        return []

    with session_scope() as s:
        contracts = s.execute(
            sa.select(ContractRow)
            .where(
                ContractRow.bot_id == bot_id,
                ContractRow.purchased_at_ms >= since_ms,
                ContractRow.purchased_at_ms <= until_ms,
            )
            .order_by(ContractRow.purchased_at_ms.asc())
        ).scalars().all()

        snapshots = s.execute(
            sa.select(BalanceSnapshotRow)
            .where(
                BalanceSnapshotRow.bot_id == bot_id,
                BalanceSnapshotRow.at_ms >= since_ms,
                BalanceSnapshotRow.at_ms <= until_ms,
            )
            .order_by(BalanceSnapshotRow.at_ms.asc())
        ).scalars().all()

    buckets: dict[int, dict[str, Any]] = {}

    def _bucket(ts: int) -> dict[str, Any]:
        key = (ts // bucket_size) * bucket_size
        if key not in buckets:
            buckets[key] = {
                "bucket_ms": key,
                # contract activity
                "pnl": 0.0, "staked": 0.0, "payout": 0.0,
                "won": 0, "lost": 0, "open": 0, "total": 0,
                "win_rate": 0.0,
                # balance bookends — null until we see a snapshot in this bucket
                "balance_open": None, "balance_close": None,
                "balance_low": None, "balance_high": None,
            }
        return buckets[key]

    for c in contracts:
        b = _bucket(c.purchased_at_ms)
        b["total"] += 1
        b["staked"] += c.purchase_price
        if c.status == "won":
            b["won"] += 1
            b["pnl"] += (c.pnl or 0.0)
            b["payout"] += (c.payout_received or 0.0)
        elif c.status == "lost":
            b["lost"] += 1
            b["pnl"] += -(c.stake or 0.0)  # actual loss = -stake (pnl column stores notional, not 0)
        else:
            b["open"] += 1

    # Snapshots are already chronological — first one we see in a bucket is open,
    # last one is close, track min/max along the way.
    for snap in snapshots:
        b = _bucket(snap.at_ms)
        v = snap.balance
        if b["balance_open"] is None:
            b["balance_open"] = v
            b["balance_low"] = v
            b["balance_high"] = v
        else:
            if v < b["balance_low"]: b["balance_low"] = v
            if v > b["balance_high"]: b["balance_high"] = v
        b["balance_close"] = v

    # Finalize: compute win_rate, sort
    results: list[dict[str, Any]] = []
    for ts in sorted(buckets.keys()):
        b = buckets[ts]
        settled = b["won"] + b["lost"]
        b["win_rate"] = b["won"] / settled if settled > 0 else 0.0
        results.append(b)
    return results


def _row_dict(r: BalanceSnapshotRow) -> dict[str, Any]:
    return {
        "id": r.id,
        "bot_id": r.bot_id,
        "balance": r.balance,
        "currency": r.currency,
        "at_ms": r.at_ms,
        "source": r.source,
    }
