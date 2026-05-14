"""Portfolio-level analytics — account balance growth and per-bot real P&L.

The contracts table stores pnl = payout_received - purchase_price for ALL
contracts, including lost ones where payout_received is the *expected* payout
(not 0).  The actual monetary impact on the Deriv account is:
  won  → +pnl  (correct: actual profit received)
  lost → -stake (lost the stake, received nothing)

This endpoint uses that corrected formula throughout.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone, date, timedelta
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends

from app.auth.deps import require
from app.auth.models import User
from app.db.engine import session_scope
from app.db.orm import BalanceSnapshotRow, BotRow, ContractRow

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

# The Brindle Trend Trader (archived, no allocation) recorded real Deriv
# account balance snapshots — the only bot whose snapshots reflect master balance.
_ANCHOR_BOT_ID = "bot_d5d3def8c650"

# Break-even win rate for Deriv binary options at ~92% payout:
# E[PnL] = 0 → p * 0.92 - (1-p) * 1 = 0 → p = 1/1.92 ≈ 52.1%
BREAK_EVEN_WIN_RATE = round(1.0 / 1.92, 4)


def _real_pnl(c: ContractRow) -> float:
    return (c.pnl or 0.0) if c.status == "won" else -(c.stake or 0.0)


def compute_portfolio_analytics() -> dict[str, Any]:
    with session_scope() as s:
        contracts = (
            s.execute(
                sa.select(ContractRow)
                .where(ContractRow.status.in_(["won", "lost"]))
                .where(ContractRow.pnl.is_not(None))
                .where(ContractRow.settled_at_ms.is_not(None))
                .order_by(ContractRow.settled_at_ms.asc())
            )
            .scalars()
            .all()
        )

        first_snap = s.execute(
            sa.select(BalanceSnapshotRow)
            .where(BalanceSnapshotRow.bot_id == _ANCHOR_BOT_ID)
            .order_by(BalanceSnapshotRow.at_ms.asc())
            .limit(1)
        ).scalar_one_or_none()

        bots = s.execute(sa.select(BotRow)).scalars().all()

    bot_names = {b.id: b.name for b in bots}

    if not contracts:
        return {"account": {}, "daily": [], "bots": []}

    # ── Group by UTC calendar day ──────────────────────────────────────────────
    daily_pnl: dict[date, float] = defaultdict(float)
    daily_won: dict[date, int] = defaultdict(int)
    daily_lost: dict[date, int] = defaultdict(int)
    bot_stats: dict[str, dict[str, Any]] = {}

    for c in contracts:
        day = datetime.fromtimestamp(c.settled_at_ms / 1000.0, tz=timezone.utc).date()
        rp = _real_pnl(c)
        daily_pnl[day] += rp
        if c.status == "won":
            daily_won[day] += 1
        else:
            daily_lost[day] += 1

        if c.bot_id not in bot_stats:
            bot_stats[c.bot_id] = {"trades": 0, "won": 0, "lost": 0, "real_pnl": 0.0, "total_stake": 0.0}
        bs = bot_stats[c.bot_id]
        bs["trades"] += 1
        bs["real_pnl"] += rp
        bs["total_stake"] += c.stake or 0.0
        if c.status == "won":
            bs["won"] += 1
        else:
            bs["lost"] += 1

    # ── Anchor balance: back-compute opening from first snapshot ───────────────
    if first_snap:
        pre_pnl = sum(_real_pnl(c) for c in contracts if c.settled_at_ms < first_snap.at_ms)
        opening_balance: float = first_snap.balance - pre_pnl
    else:
        opening_balance = 0.0

    # ── Build daily rows with running balance ──────────────────────────────────
    all_days = sorted(daily_pnl.keys())
    start_day = all_days[0]
    end_day = datetime.now(timezone.utc).date()

    running = opening_balance
    peak = running
    max_drawdown = 0.0
    daily_rows: list[dict[str, Any]] = []

    current_date = start_day
    while current_date <= end_day:
        pnl_today = daily_pnl.get(current_date, 0.0)
        won = daily_won.get(current_date, 0)
        lost = daily_lost.get(current_date, 0)
        trades = won + lost

        running += pnl_today
        if running > peak:
            peak = running
        dd = running - peak
        if dd < max_drawdown:
            max_drawdown = dd

        daily_rows.append({
            "date": current_date.isoformat(),
            "trades": trades,
            "won": won,
            "lost": lost,
            "real_pnl": round(pnl_today, 2),
            "win_rate": round(won / trades, 4) if trades > 0 else None,
            "running_balance": round(running, 2),
        })
        current_date += timedelta(days=1)

    # ── Per-bot sorted by real P&L ─────────────────────────────────────────────
    bots_list = []
    for bot_id, stats in sorted(bot_stats.items(), key=lambda x: x[1]["real_pnl"], reverse=True):
        settled = stats["won"] + stats["lost"]
        wr = stats["won"] / settled if settled > 0 else 0.0
        avg_stake = stats["total_stake"] / stats["trades"] if stats["trades"] > 0 else 0.0
        bots_list.append({
            "bot_id": bot_id,
            "name": bot_names.get(bot_id, bot_id),
            "trades": stats["trades"],
            "won": stats["won"],
            "lost": stats["lost"],
            "win_rate": round(wr, 4),
            "real_pnl": round(stats["real_pnl"], 2),
            "avg_stake": round(avg_stake, 2),
        })

    total_won = sum(b["won"] for b in bots_list)
    total_lost = sum(b["lost"] for b in bots_list)
    total_trades = total_won + total_lost
    overall_wr = total_won / total_trades if total_trades > 0 else 0.0
    net_change = running - opening_balance
    net_change_pct = (net_change / opening_balance * 100) if opening_balance else None
    max_dd_pct = (max_drawdown / peak * 100) if peak > 0 else None

    return {
        "account": {
            "opening_balance": round(opening_balance, 2),
            "current_balance": round(running, 2),
            "peak_balance": round(peak, 2),
            "net_change": round(net_change, 2),
            "net_change_pct": round(net_change_pct, 2) if net_change_pct is not None else None,
            "max_drawdown": round(max_drawdown, 2),
            "max_drawdown_pct": round(max_dd_pct, 2) if max_dd_pct is not None else None,
            "total_trades": total_trades,
            "total_won": total_won,
            "total_lost": total_lost,
            "overall_win_rate": round(overall_wr, 4),
            "break_even_win_rate": BREAK_EVEN_WIN_RATE,
        },
        "daily": daily_rows,
        "bots": bots_list,
    }


@router.get("/analytics")
async def portfolio_analytics(_: User = Depends(require("bot:read"))) -> dict:
    return compute_portfolio_analytics()
