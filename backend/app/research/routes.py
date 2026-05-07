from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.deps import require
from app.auth.models import User
from app.research.runner import BacktestManifest, BacktestMetrics, run_backtest

router = APIRouter(prefix="/api/research", tags=["research"])

EXPERIMENTS_DIR = Path("experiments")


class RunBacktestBody(BaseModel):
    strategy_id: str
    params: dict = {}
    symbols: list[str]
    bars: int = 500
    seed: str = "backtest"
    risk: dict = {}
    save: bool = True  # persist results to experiments/<run_id>/


@router.post("/backtest", response_model=dict)
async def run_backtest_endpoint(
    body: RunBacktestBody, _: User = Depends(require("bot:read"))
) -> dict:
    manifest = BacktestManifest(
        strategy_id=body.strategy_id,
        params=body.params,
        symbols=body.symbols,
        bars=body.bars,
        seed=body.seed,
        risk=body.risk,
    )
    try:
        out_dir = (EXPERIMENTS_DIR / manifest.run_id) if body.save else None
        metrics = run_backtest(manifest, output_dir=out_dir)
    except Exception as e:
        raise HTTPException(400, str(e))
    return metrics.to_dict()


@router.get("/backtests", response_model=list[dict])
async def list_backtests(_: User = Depends(require("bot:read"))) -> list[dict]:
    if not EXPERIMENTS_DIR.exists():
        return []
    runs = []
    for run_dir in sorted(EXPERIMENTS_DIR.iterdir(), reverse=True):
        metrics_file = run_dir / "metrics.json"
        if metrics_file.exists():
            import json
            runs.append(json.loads(metrics_file.read_text()))
    return runs


@router.get("/observation_report", response_model=list[dict])
async def get_observation_report(
    since_hours: int = 24, _: User = Depends(require("bot:read"))
) -> list[dict]:
    from app.bots import service as bot_service
    from app.configs import service as config_service
    from app.execution import contracts as contracts_svc
    from app.alerts import service as alert_service
    from app.research import observation as obs_store
    from app.core.time import now_epoch_ms
    from app.db.orm import AlertRow
    from app.db.engine import session_scope
    from sqlalchemy import select, func

    since_ms = now_epoch_ms() - (since_hours * 3600 * 1000)
    bots = bot_service.list_bots()
    # Filter non-archived
    from app.bots.models import BotState
    bots = [b for b in bots if b.state != BotState.ARCHIVED]

    report = []
    for bot in bots:
        # 1. Performance
        summ = contracts_svc.summary(bot.id, since_ms=since_ms)
        win_rate = 0.0
        settled = summ["won_count"] + summ["lost_count"]
        if settled > 0:
            win_rate = summ["won_count"] / settled
        
        recent = contracts_svc.list_recent(bot.id, limit=1)
        last_trade_at = recent[0]["purchased_at_ms"] if recent else None

        # 2. Risk / Alerts
        rejection_count = 0
        auto_pause_count = 0
        with session_scope() as s:
            rejection_count = s.execute(
                select(func.count(AlertRow.id)).where(
                    AlertRow.bot_id == bot.id,
                    AlertRow.created_at_ms >= since_ms,
                    AlertRow.message.like("risk rejection%")
                )
            ).scalar() or 0
            auto_pause_count = s.execute(
                select(func.count(AlertRow.id)).where(
                    AlertRow.bot_id == bot.id,
                    AlertRow.created_at_ms >= since_ms,
                    AlertRow.message.like("auto-pausing bot%")
                )
            ).scalar() or 0

        # 3. Signals / Ticks
        histogram = obs_store.get_histogram(bot.id)
        tick_count = obs_store.get_tick_count(bot.id)

        # 4. Config metadata
        active = config_service.active_version(bot.id)
        strategy_id = active.config.strategy.strategy_id if active else "unknown"
        symbols = active.config.symbols if active else []

        report.append({
            "bot_id": bot.id,
            "name": bot.name,
            "strategy_id": strategy_id,
            "symbols": symbols,
            "trades": summ["total_count"],
            "win_rate": win_rate,
            "realized_pnl": summ["total_pnl"],
            "rejection_count": rejection_count,
            "auto_pauses": auto_pause_count,
            "last_trade_at_ms": last_trade_at,
            "tick_count": tick_count,
            "signal_status_histogram": histogram
        })
    
    return report
