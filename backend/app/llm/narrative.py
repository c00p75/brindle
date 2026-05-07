"""Generate a plain-English narrative summary of a bot's performance window.

Inputs (gathered server-side, not by the LLM):
  - Contract analytics buckets (hourly or daily) for the window
  - Balance series start/end values
  - Top winners and top losers if any

Output: a 2-4 paragraph human-readable narrative. Markdown-formatted.
The LLM only sees aggregate, deterministic numbers — it never sees raw
trade-by-trade data, so it can't hallucinate specific contracts.
"""
from __future__ import annotations

import logging
from typing import Any

from app.llm import client as llm_client

log = logging.getLogger("llm.narrative")

_SYSTEM = """You are a trading-performance commentator for Brindle, a paper-
first algo trading platform.

You will be given a JSON summary of a bot's performance window. Produce a
2-4 paragraph narrative that:
  - States the headline result (net P&L, win rate vs the 52% binary-option
    breakeven threshold) in the FIRST sentence.
  - Identifies the best and worst time buckets and what they suggest.
  - Notes any divergence between tracked-contract P&L and the real broker
    balance change (the broker balance is ground truth).
  - Closes with one CONCRETE suggestion (e.g. "consider tightening
    cooldown_ticks", "win rate is below breakeven — the strategy is not
    profitable on this instrument").

Style:
  - Plain English, NO disclaimers, NO "remember that past performance".
  - Markdown formatting: bold for key numbers, no headings.
  - Concise — 4 paragraphs max, never longer than 200 words total.
  - If P&L is negative, do NOT sugarcoat. Say it lost money.
  - Do NOT invent numbers — if a field is missing or zero, work around it.
"""


def _build_summary_payload(
    *,
    bot_name: str,
    window_label: str,
    contracts_summary: dict[str, Any],
    analytics: list[dict[str, Any]],
    balance_start: float | None,
    balance_end: float | None,
    currency: str | None,
) -> dict[str, Any]:
    """Reduce raw data into a compact, fact-only dict that fits in the prompt."""
    pnl = contracts_summary.get("realized_pnl", 0.0)
    win = contracts_summary.get("won_count", 0)
    lost = contracts_summary.get("lost_count", 0)
    settled = win + lost
    win_rate = (win / settled) if settled > 0 else 0.0

    # Top 3 best and worst hours by realized P&L
    by_pnl = sorted(analytics, key=lambda b: b.get("pnl", 0.0))
    worst = by_pnl[:3]
    best = by_pnl[-3:][::-1]

    real_change = None
    if balance_start is not None and balance_end is not None:
        real_change = balance_end - balance_start

    return {
        "bot_name": bot_name,
        "window": window_label,
        "contracts": {
            "total": contracts_summary.get("total_count", 0),
            "won": win,
            "lost": lost,
            "open": contracts_summary.get("open_count", 0),
            "win_rate_pct": round(win_rate * 100, 1),
            "tracked_pnl": round(pnl, 2),
            "total_staked": round(contracts_summary.get("total_staked", 0.0), 2),
        },
        "broker_balance": {
            "currency": currency,
            "start": balance_start,
            "end": balance_end,
            "real_change": real_change,
        },
        "buckets_analysed": len(analytics),
        "best_buckets": [
            {"bucket_ms": b["bucket_ms"], "pnl": round(b.get("pnl", 0.0), 2),
             "won": b.get("won", 0), "lost": b.get("lost", 0)}
            for b in best
        ],
        "worst_buckets": [
            {"bucket_ms": b["bucket_ms"], "pnl": round(b.get("pnl", 0.0), 2),
             "won": b.get("won", 0), "lost": b.get("lost", 0)}
            for b in worst
        ],
        "binary_option_breakeven_pct": 52.0,
    }


async def generate(*, bot_name: str, window_label: str,
                   contracts_summary: dict[str, Any],
                   analytics: list[dict[str, Any]],
                   balance_start: float | None,
                   balance_end: float | None,
                   currency: str | None) -> str:
    payload = _build_summary_payload(
        bot_name=bot_name, window_label=window_label,
        contracts_summary=contracts_summary, analytics=analytics,
        balance_start=balance_start, balance_end=balance_end, currency=currency,
    )
    import json
    user_msg = f"Summarise this performance window:\n\n```json\n{json.dumps(payload, indent=2)}\n```"
    return await llm_client.complete(
        system=_SYSTEM, user=user_msg, temperature=0.4, max_tokens=600,
    )
