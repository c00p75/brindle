"""Deriv contract lifecycle persistence + polling-based settlement tracker.

Each Deriv binary-option BUY produces one ContractRow. The runtime later
polls open contracts to detect settlement (won/lost) and update PnL.

Why polling, not WebSocket subscriptions:
  - The runtime already shares a Deriv WS connection per bot.
  - `proposal_open_contract` push subscriptions add complexity to the
    multiplexed _send/_recv design and double the message volume.
  - Polling once per N ticks is plenty for 5-minute contracts.
"""
from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

from app.core.time import now_epoch_ms
from app.db.engine import session_scope
from app.db.orm import ContractRow

log = logging.getLogger("contracts")


def record_purchase(
    *,
    bot_id: str,
    contract_id: str,
    client_order_id: str | None,
    symbol: str,
    contract_type: str,
    stake: float,
    expected_payout: float,
    purchase_price: float,
    expires_at_ms: int | None,
) -> None:
    """Persist a freshly bought Deriv contract."""
    with session_scope() as s:
        existing = s.get(ContractRow, contract_id)
        if existing is not None:
            return
        s.add(ContractRow(
            contract_id=contract_id,
            bot_id=bot_id,
            client_order_id=client_order_id,
            symbol=symbol,
            contract_type=contract_type,
            stake=stake,
            expected_payout=expected_payout,
            purchase_price=purchase_price,
            payout_received=None,
            pnl=None,
            status="open",
            purchased_at_ms=now_epoch_ms(),
            expires_at_ms=expires_at_ms,
            settled_at_ms=None,
        ))
        s.flush()


def settle(*, contract_id: str, payout_received: float, status: str) -> None:
    """Mark a contract as won/lost with realized payout.

    The Deriv API returns the notional (expected) payout in the `payout` field
    for both won AND lost contracts — not 0 for losses. Store it as-is in
    payout_received for reference, but compute pnl from actual monetary impact:
      won  → payout_received - purchase_price  (actual profit)
      lost → -stake  (lost the stake, received nothing)
    """
    with session_scope() as s:
        row = s.get(ContractRow, contract_id)
        if row is None or row.status != "open":
            return
        row.payout_received = payout_received
        if status == "lost":
            row.pnl = -(row.stake or row.purchase_price)
        else:
            row.pnl = payout_received - row.purchase_price
        row.status = status
        row.settled_at_ms = now_epoch_ms()
        s.flush()


def list_open_ids(bot_id: str) -> list[str]:
    with session_scope() as s:
        rows = s.execute(
            sa.select(ContractRow.contract_id).where(
                ContractRow.bot_id == bot_id,
                ContractRow.status == "open",
            )
        ).all()
    return [r[0] for r in rows]


def summary(bot_id: str, *, since_ms: int | None = None,
            until_ms: int | None = None) -> dict[str, Any]:
    """Aggregate stats for the bot's contracts within an optional time window.

    Window is applied to `purchased_at_ms`. Without bounds the result is
    all-time. Open contracts straddling the window edge are still included
    if they were purchased within it.
    """
    with session_scope() as s:
        q = sa.select(ContractRow).where(ContractRow.bot_id == bot_id)
        if since_ms is not None:
            q = q.where(ContractRow.purchased_at_ms >= since_ms)
        if until_ms is not None:
            q = q.where(ContractRow.purchased_at_ms <= until_ms)
        rows = s.execute(q).scalars().all()
    open_ = [r for r in rows if r.status == "open"]
    won = [r for r in rows if r.status == "won"]
    lost = [r for r in rows if r.status == "lost"]
    # Compute actual monetary P&L regardless of what's stored in the pnl column.
    # Historical lost contracts have pnl = notional_payout - stake (wrong),
    # so always use: won → stored pnl, lost → -stake.
    total_pnl = (
        sum((r.pnl or 0.0) for r in won)
        + sum(-(r.stake or 0.0) for r in lost)
    )
    return {
        "open_count": len(open_),
        "won_count": len(won),
        "lost_count": len(lost),
        "total_count": len(rows),
        "total_staked": sum(r.purchase_price for r in rows),
        "total_payout": sum((r.payout_received or 0.0) for r in rows),
        "realized_pnl": total_pnl,
        "win_rate": (len(won) / (len(won) + len(lost))) if (won or lost) else 0.0,
        "since_ms": since_ms,
        "until_ms": until_ms,
    }


def list_recent(bot_id: str, limit: int = 50, since_ms: int | None = None,
                until_ms: int | None = None) -> list[dict[str, Any]]:
    with session_scope() as s:
        q = sa.select(ContractRow).where(ContractRow.bot_id == bot_id)
        if since_ms is not None:
            q = q.where(ContractRow.purchased_at_ms >= since_ms)
        if until_ms is not None:
            q = q.where(ContractRow.purchased_at_ms <= until_ms)
        q = q.order_by(ContractRow.purchased_at_ms.desc()).limit(limit)
        rows = s.execute(q).scalars().all()
    return [_to_dict(r) for r in rows]


def _to_dict(r: ContractRow) -> dict[str, Any]:
    return {
        "contract_id": r.contract_id,
        "bot_id": r.bot_id,
        "symbol": r.symbol,
        "contract_type": r.contract_type,
        "stake": r.stake,
        "expected_payout": r.expected_payout,
        "purchase_price": r.purchase_price,
        "payout_received": r.payout_received,
        "pnl": r.pnl,
        "status": r.status,
        "purchased_at_ms": r.purchased_at_ms,
        "expires_at_ms": r.expires_at_ms,
        "settled_at_ms": r.settled_at_ms,
    }
