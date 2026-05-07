"""Pre-apply sanity check on a config diff. Surfaces foot-guns before
the user types 'APPLY RISK CHANGE'.

Inputs:
  - The proposed full config (BotConfig as dict)
  - The diff vs the active config (DiffEntry list)

LLM returns warnings keyed by severity. Frontend should display these as
a banner above the Apply button — they are advisory, not blocking. The
existing typed-confirmation gate is still the hard guard.
"""
from __future__ import annotations

import logging
from typing import Any

from app.llm import client as llm_client

log = logging.getLogger("llm.config_sanity")

_SYSTEM = """You are a config-review assistant for the Brindle paper-first
trading platform. Your job: review a proposed bot configuration change
and flag obvious foot-guns BEFORE the user applies it.

You'll receive:
  - The full proposed config (strategy, params, risk limits, broker, symbols)
  - The diff from the currently-active config

Return ONE JSON object:

{
  "warnings": [
    {
      "severity": "info" | "warning" | "critical",
      "field": "risk.max_daily_loss",   // dotted path or "<config>"
      "message": "human-readable single sentence"
    },
    ...
  ],
  "ok_to_apply": true | false,
  "summary": "one short sentence overall"
}

WHAT TO FLAG:
  CRITICAL — definitely a foot-gun:
    - kill_switch turned OFF if it was previously ON
    - max_drawdown_pct >= 90 (effectively no drawdown protection)
    - max_daily_loss > 10× the typical broker balance
    - max_open_orders > 100 with binary-option contracts
    - Strategy switched but params still match the old strategy's schema

  WARNING — non-obvious but probably wrong:
    - max_position_notional > max_total_exposure (impossible by validator
      but flag if approaching)
    - cooldown_ticks = 0 on a strategy that fires every tick
    - qty values that don't match the broker's lot size convention
    - max_consecutive_losses set to a very high number (>50) effectively
      disabling the breaker

  INFO — worth pointing out:
    - Significant changes to risk limits (>2× looser than before)
    - First-time strategy choice (note that it should be backtested first)

RULES:
  - Cap warnings at 6.
  - If the config looks fine, return an empty warnings array and ok_to_apply=true.
  - Do NOT block on style preferences. Stick to genuine risk concerns.
  - Output STRICTLY one JSON object, no prose outside it.
"""


async def review(*, proposed_config: dict[str, Any], diff: list[dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(proposed_config, dict):
        return {"warnings": [], "ok_to_apply": True, "summary": "no config to review"}
    import json
    user_msg = (
        "Review this proposed configuration change.\n\n"
        f"PROPOSED CONFIG:\n```json\n{json.dumps(proposed_config, indent=2)}\n```\n\n"
        f"DIFF FROM ACTIVE:\n```json\n{json.dumps(diff, indent=2)}\n```"
    )
    result = await llm_client.complete_json(
        system=_SYSTEM, user=user_msg, temperature=0.1, max_tokens=1000,
    )
    if "warnings" not in result:
        # Defensive fallback for schema drift
        return {"warnings": [], "ok_to_apply": True,
                "summary": result.get("error") or "review unavailable"}
    return result
