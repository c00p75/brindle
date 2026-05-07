"""Cluster recent alerts and surface a concise insight digest.

Approach:
  1. Pull the last N alerts from the alerts table.
  2. Send their messages + severities to Groq with a strict JSON-mode schema.
  3. LLM returns groups (similar messages collapsed), each with:
       - a representative pattern
       - the count of alerts in the group
       - a one-sentence likely cause
       - a suggested action
  4. Frontend renders these as banners on the alerts page.

We never send alert IDs or PII to the LLM — just the message text and
severity. The frontend re-joins by message-text matching for navigation.
"""
from __future__ import annotations

import logging
from typing import Any

from app.llm import client as llm_client

log = logging.getLogger("llm.alert_insights")

_SYSTEM = """You are an alert triage assistant for the Brindle trading platform.

You'll receive a JSON list of recent alerts ({severity, source, message, count}).
Your job: cluster duplicates and near-duplicates, identify likely root causes,
and propose actions.

Return ONE JSON object with this shape:

{
  "groups": [
    {
      "pattern": "short human-readable pattern, e.g. 'Deriv WebSocket reconnect failures'",
      "count": <integer total alerts in this group>,
      "severity": "info" | "warning" | "critical",
      "likely_cause": "one short sentence",
      "suggested_action": "one short imperative sentence"
    },
    ...
  ],
  "summary": "one sentence overall assessment, e.g. 'Mostly transient, no action required.'"
}

RULES:
- Return STRICTLY a single JSON object — no prose outside it.
- Group aggressively but don't lump genuinely different issues together.
- Cap groups at 6. Most-frequent first.
- If there are zero alerts, return {"groups": [], "summary": "No alerts in the window."}.
- Do NOT invent alerts that weren't in the input.
"""


async def cluster_alerts(alerts: list[dict[str, Any]]) -> dict[str, Any]:
    """alerts is a list of {severity, source, message, ...}.
    Returns the LLM's clustering plus echoes input count."""
    if not alerts:
        return {"groups": [], "summary": "No alerts in the window.", "input_count": 0}

    # Trim each alert to just the fields the LLM needs — keeps prompt small.
    payload = [
        {
            "severity": a.get("severity", "info"),
            "source": a.get("source", ""),
            "message": (a.get("message") or "")[:300],
        }
        for a in alerts
    ]
    import json
    user_msg = (
        f"Here are the most recent {len(payload)} alerts. Cluster them.\n\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```"
    )
    result = await llm_client.complete_json(
        system=_SYSTEM, user=user_msg, temperature=0.2, max_tokens=1500,
    )
    if "error" in result and "groups" not in result:
        return {"groups": [], "summary": f"LLM error: {result['error']}",
                "input_count": len(payload)}
    result["input_count"] = len(payload)
    return result
