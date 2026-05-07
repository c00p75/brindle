"""HTTP routes for LLM-powered features.

All endpoints fail gracefully if GROQ_API_KEY is missing — they return a
JSON error rather than 500. Frontend treats that as "feature unavailable".
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.auth.deps import require
from app.auth.models import User
from app.llm import alert_insights, config_sanity, narrative, strategy_gen
from app.llm.client import LLMNotConfigured

router = APIRouter(prefix="/api/llm", tags=["llm"])


# ---------------------------------------------------------------------------
# #2 — Strategy generator
# ---------------------------------------------------------------------------

@router.post("/strategies/generate")
async def generate_strategy(
    body: dict = Body(...),
    _: User = Depends(require("config:draft")),
):
    """NL description → validated Python strategy file in app/strategies/user/.

    Admin-equivalent permission required (config:draft). Generated code is
    AST-validated against an import whitelist and a banned-call list before
    being written to disk.
    """
    description = (body.get("description") or "").strip()
    if not description:
        raise HTTPException(400, "description is required")
    try:
        return await strategy_gen.generate_strategy(description)
    except LLMNotConfigured as e:
        raise HTTPException(503, str(e))


# ---------------------------------------------------------------------------
# #4 — Performance narrative
# ---------------------------------------------------------------------------

@router.get("/bots/{bot_id}/narrative")
async def bot_narrative(
    bot_id: str,
    since_ms: int = Query(...),
    until_ms: int = Query(...),
    granularity: str = Query("hour"),
    _: User = Depends(require("bot:read")),
):
    """Generate plain-English performance commentary for a bot's window."""
    from app.bots import service as bot_service
    from app.execution import balance_history
    from app.execution import contracts as contracts_svc

    bot = bot_service.get(bot_id)
    if bot is None:
        raise HTTPException(404, "bot not found")

    contracts = contracts_svc.summary(bot_id, since_ms=since_ms, until_ms=until_ms)
    buckets = balance_history.analytics(
        bot_id=bot_id, since_ms=since_ms, until_ms=until_ms, granularity=granularity,
    )
    series = balance_history.history(
        bot_id=bot_id, since_ms=since_ms, until_ms=until_ms, max_points=2,
    )
    bal_start = float(series[0]["balance"]) if series else None
    bal_end = float(series[-1]["balance"]) if series else None
    currency = (series[-1]["currency"] if series else None)

    window_label = f"{since_ms} → {until_ms} ({granularity} buckets)"
    try:
        text = await narrative.generate(
            bot_name=bot.name, window_label=window_label,
            contracts_summary=contracts, analytics=buckets,
            balance_start=bal_start, balance_end=bal_end, currency=currency,
        )
    except LLMNotConfigured as e:
        raise HTTPException(503, str(e))
    return {"narrative_md": text, "window": {"since_ms": since_ms, "until_ms": until_ms}}


# ---------------------------------------------------------------------------
# #5 — Alert insights
# ---------------------------------------------------------------------------

@router.get("/alerts/insights")
async def alerts_insights(
    limit: int = Query(50, le=200),
    _: User = Depends(require("bot:read")),
):
    """Cluster recent alerts and surface a digest with likely causes."""
    from app.alerts import service as alert_service
    alerts = alert_service.list_alerts()[:limit]
    payload = [
        {
            "severity": a.severity.value if hasattr(a.severity, "value") else str(a.severity),
            "source": a.source,
            "message": a.message,
        }
        for a in alerts
    ]
    try:
        return await alert_insights.cluster_alerts(payload)
    except LLMNotConfigured as e:
        raise HTTPException(503, str(e))


# ---------------------------------------------------------------------------
# #6 — Config sanity check
# ---------------------------------------------------------------------------

@router.post("/configs/sanity-check")
async def sanity_check(
    body: dict = Body(...),
    _: User = Depends(require("config:draft")),
):
    """Pre-apply review. Body: {config: BotConfig, diff: DiffEntry[]}."""
    proposed = body.get("config") or {}
    diff = body.get("diff") or []
    try:
        return await config_sanity.review(proposed_config=proposed, diff=diff)
    except LLMNotConfigured as e:
        raise HTTPException(503, str(e))
