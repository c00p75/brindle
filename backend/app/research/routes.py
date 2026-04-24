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
