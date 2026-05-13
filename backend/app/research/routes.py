import asyncio
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


class WalkForwardBody(BaseModel):
    strategy_id: str
    symbol: str
    bars: int = 1000
    param_grid: list[dict]
    n_folds: int = 4
    train_ratio: float = 0.7
    min_test_trades: int = 5


@router.post("/walk_forward", response_model=dict)
async def walk_forward_endpoint(
    body: WalkForwardBody, _: User = Depends(require("bot:read"))
) -> dict:
    from app.research.deriv_history import fetch_historical_bars
    from app.research.walk_forward import walk_forward

    def _run() -> dict:
        all_bars = fetch_historical_bars(body.symbol, body.bars)
        report = walk_forward(
            strategy_id=body.strategy_id,
            symbol=body.symbol,
            all_bars=all_bars,
            param_grid=body.param_grid,
            n_folds=body.n_folds,
            train_ratio=body.train_ratio,
            min_test_trades=body.min_test_trades,
        )
        folds = [
            {
                "fold_index": f.fold_index,
                "train_bars": f.train_bars,
                "test_bars": f.test_bars,
                "best_train_params": f.best_train_params,
                "train_win_rate": round(f.train_metrics.win_rate, 4),
                "test_win_rate": round(f.test_metrics.win_rate, 4),
                "train_pnl": round(f.train_metrics.total_realized_pnl, 4),
                "test_pnl": round(f.test_metrics.total_realized_pnl, 4),
                "train_trades": f.train_metrics.win_trades + f.train_metrics.loss_trades,
                "test_trades": f.test_metrics.win_trades + f.test_metrics.loss_trades,
            }
            for f in report.folds
        ]
        return {
            "verdict": report.verdict,
            "strategy_id": report.strategy_id,
            "symbol": report.symbol,
            "total_bars": report.total_bars,
            "mean_test_win_rate": round(report.mean_test_win_rate, 4),
            "aggregate_z_score": round(report.aggregate_z_score, 4),
            "per_fold_win_rate_std": round(report.per_fold_win_rate_std, 4),
            "folds": folds,
        }

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _run)
    except Exception as e:
        raise HTTPException(400, str(e))
    return result


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
