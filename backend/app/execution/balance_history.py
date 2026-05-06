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


def analytics(*, bot_id: str, since_ms: int, until_ms: int,
              granularity: str = "hour") -> list[dict[str, Any]]:
    """Return performance aggregates bucketed by hour or day.

    Granularity: 'hour' or 'day'.
    Returns: list of buckets, each with {bucket_ms, win_rate, pnl, staked, volume, ...}
    """
    from app.db.orm import ContractRow, FillRow
    with session_scope() as s:
        # 1. Fetch relevant contracts and fills in the window
        # For Deriv bots, ContractRow is the source of truth for P&L.
        q_contracts = (
            sa.select(ContractRow)
            .where(ContractRow.bot_id == bot_id, ContractRow.purchased_at_ms >= since_ms,
                   ContractRow.purchased_at_ms <= until_ms)
            .order_by(ContractRow.purchased_at_ms.asc())
        )
        contracts = s.execute(q_contracts).scalars().all()

        # For Forex bots, FillRow P&L is materialized in PositionRow, but for history
        # we'd need to reconstruct it or look at realized_pnl changes.
        # Currently, we focus on Deriv contracts as they are the main use case.

    if not contracts:
        return []

    # Bucketing logic
    bucket_size = 3600_000 if granularity == "hour" else 86400_000
    buckets: dict[int, dict[str, Any]] = {}

    for c in contracts:
        bucket_ts = (c.purchased_at_ms // bucket_size) * bucket_size
        if bucket_ts not in buckets:
            buckets[bucket_ts] = {
                "bucket_ms": bucket_ts,
                "pnl": 0.0,
                "staked": 0.0,
                "won": 0,
                "lost": 0,
                "total": 0,
            }
        b = buckets[bucket_ts]
        b["total"] += 1
        b["staked"] += c.purchase_price
        if c.status == "won":
            b["won"] += 1
            b["pnl"] += (c.pnl or 0.0)
        elif c.status == "lost":
            b["lost"] += 1
            b["pnl"] += (c.pnl or 0.0)

    # Convert to sorted list and add win_rate
    results = []
    for ts in sorted(buckets.keys()):
        b = buckets[ts]
        win_count = b["won"]
        loss_count = b["lost"]
        b["win_rate"] = win_count / (win_count + loss_count) if (win_count + loss_count) > 0 else 0.0
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
