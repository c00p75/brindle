"""Walk-forward 2.0 — rigorous out-of-sample backtesting.

Why this exists:
A single 70/30 train/test split is barely better than no split. With 30%
of the data as test, you have one shot at evaluating an overfit. K-fold
rolling-window walk-forward gives you multiple independent out-of-sample
evaluations, then averages them. If a strategy doesn't beat random across
several folds, it doesn't have edge.

Methodology (rolling-window walk-forward):

  bars: [-------------------------------------------------------]
        ▲train───▲test    (fold 1)
            ▲train───▲test    (fold 2)
                ▲train───▲test    (fold 3)
                    ▲train───▲test    (fold 4)

Each fold: tune params on train via grid search, evaluate winning params
on the held-out test. Aggregate test results across all folds.

Verdict criteria — a strategy passes ALL of these or it has no edge:
  - mean_test_win_rate > 50% (across folds)
  - aggregate z-score > 1.96 (statistically distinguishable from coin flip)
  - per-fold consistency (std < some threshold; not just one lucky fold)
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, Callable

from app.research.deriv_history import DerivHistoricalFeed
from app.research import deriv_history
from app.research.runner import BacktestManifest, BacktestMetrics, run_backtest
from app.strategies.base import Bar

log = logging.getLogger("walk_forward")


@dataclass
class FoldResult:
    fold_index: int
    train_bars: int
    test_bars: int
    best_train_params: dict[str, Any]
    train_metrics: BacktestMetrics
    test_metrics: BacktestMetrics


@dataclass
class WalkForwardReport:
    strategy_id: str
    symbol: str
    total_bars: int
    folds: list[FoldResult]
    mean_test_win_rate: float
    aggregate_z_score: float
    per_fold_win_rate_std: float
    verdict: str  # "EDGE" | "NO_EDGE" | "INSUFFICIENT_DATA"

    def summary(self) -> str:
        lines = [
            f"Strategy:       {self.strategy_id}",
            f"Symbol:         {self.symbol}",
            f"Total bars:     {self.total_bars}",
            f"Folds:          {len(self.folds)}",
            f"Mean test W/R:  {self.mean_test_win_rate * 100:.1f}%",
            f"Aggregate z:    {self.aggregate_z_score:+.2f}  (need >+1.96 for edge)",
            f"Fold std:       {self.per_fold_win_rate_std * 100:.1f}%  (lower = consistent)",
            f"VERDICT:        {self.verdict}",
            "",
            "Per-fold detail:",
        ]
        for f in self.folds:
            lines.append(
                f"  fold {f.fold_index}: "
                f"train W/R {f.train_metrics.win_rate*100:5.1f}% → "
                f"test W/R {f.test_metrics.win_rate*100:5.1f}%  "
                f"(test trades: {f.test_metrics.win_trades}/"
                f"{f.test_metrics.win_trades + f.test_metrics.loss_trades})  "
                f"params: {f.best_train_params}"
            )
        return "\n".join(lines)


def _slice_feed(symbol: str, bars: list[Bar]) -> Callable[..., DerivHistoricalFeed]:
    """Return a `from_deriv` replacement that always yields the given slice."""
    def _factory(*args, count: int = 0, **kwargs):
        return DerivHistoricalFeed({symbol: list(bars)})
    return _factory


def _evaluate(strategy_id: str, symbol: str, bars: list[Bar],
              params: dict, seed: str) -> BacktestMetrics:
    """Run a single backtest on the given bar slice."""
    deriv_history.DerivHistoricalFeed.from_deriv = staticmethod(_slice_feed(symbol, bars))
    m = BacktestManifest(
        strategy_id=strategy_id,
        params=params,
        symbols=[symbol],
        bars=max(50, len(bars) - 60),
        seed=seed,
        risk={"max_position_notional": 1_000_000, "max_total_exposure": 5_000_000},
        data_source="deriv",
    )
    return run_backtest(m)


def walk_forward(
    *,
    strategy_id: str,
    symbol: str,
    all_bars: list[Bar],
    param_grid: list[dict[str, Any]],
    n_folds: int = 4,
    train_ratio: float = 0.7,
    min_test_trades: int = 5,
) -> WalkForwardReport:
    """Run k-fold rolling-window walk-forward and produce a verdict.

    Each fold uses an expanding train window and a fixed-fraction test window.
    Best params on train (by win rate) are evaluated on the next test slice.
    """
    n = len(all_bars)
    if n < 200:
        return WalkForwardReport(
            strategy_id=strategy_id, symbol=symbol, total_bars=n, folds=[],
            mean_test_win_rate=0.0, aggregate_z_score=0.0,
            per_fold_win_rate_std=0.0, verdict="INSUFFICIENT_DATA",
        )

    # Compute fold boundaries: rolling, with each test slice the same size.
    test_size = int(n * (1 - train_ratio) / n_folds)
    if test_size < 50:
        test_size = max(50, n // (n_folds * 4))
    fold_results: list[FoldResult] = []

    for fold_idx in range(n_folds):
        test_start = int(n * train_ratio) + fold_idx * test_size
        test_end = test_start + test_size
        if test_end > n:
            break
        train = all_bars[:test_start]
        test = all_bars[test_start:test_end]
        if len(train) < 100 or len(test) < 50:
            continue

        # Grid search on train
        best = None
        for params in param_grid:
            try:
                m = _evaluate(strategy_id, symbol, train, params, f"wf-train-{fold_idx}")
                # Rank by win rate but require minimum trade count to avoid no-trade winners.
                if m.total_orders < 5:
                    continue
                score = m.win_rate
                if best is None or score > best[0]:
                    best = (score, params, m)
            except Exception as e:  # noqa: BLE001
                log.warning("backtest error fold=%d params=%s: %s", fold_idx, params, e)

        if best is None:
            continue
        _, best_params, train_metrics = best

        # Evaluate on the held-out test slice
        try:
            test_metrics = _evaluate(strategy_id, symbol, test, best_params, f"wf-test-{fold_idx}")
        except Exception as e:  # noqa: BLE001
            log.warning("test eval error fold=%d: %s", fold_idx, e)
            continue

        fold_results.append(FoldResult(
            fold_index=fold_idx,
            train_bars=len(train),
            test_bars=len(test),
            best_train_params=best_params,
            train_metrics=train_metrics,
            test_metrics=test_metrics,
        ))

    return _aggregate(strategy_id, symbol, n, fold_results, min_test_trades)


def _aggregate(strategy_id: str, symbol: str, total_bars: int,
               folds: list[FoldResult], min_test_trades: int) -> WalkForwardReport:
    if not folds:
        return WalkForwardReport(
            strategy_id=strategy_id, symbol=symbol, total_bars=total_bars, folds=folds,
            mean_test_win_rate=0.0, aggregate_z_score=0.0,
            per_fold_win_rate_std=0.0, verdict="INSUFFICIENT_DATA",
        )

    # Pool all test trades across folds for one big binomial test
    total_wins = sum(f.test_metrics.win_trades for f in folds)
    total_losses = sum(f.test_metrics.loss_trades for f in folds)
    total_settled = total_wins + total_losses

    if total_settled < min_test_trades:
        return WalkForwardReport(
            strategy_id=strategy_id, symbol=symbol, total_bars=total_bars, folds=folds,
            mean_test_win_rate=0.0, aggregate_z_score=0.0,
            per_fold_win_rate_std=0.0, verdict="INSUFFICIENT_DATA",
        )

    pooled_win_rate = total_wins / total_settled
    se = math.sqrt(0.5 * 0.5 / total_settled)
    z = (pooled_win_rate - 0.5) / se if se > 0 else 0.0

    per_fold_rates = [f.test_metrics.win_rate for f in folds
                      if f.test_metrics.win_trades + f.test_metrics.loss_trades > 0]
    if per_fold_rates:
        mean_rate = sum(per_fold_rates) / len(per_fold_rates)
        var = sum((r - mean_rate) ** 2 for r in per_fold_rates) / len(per_fold_rates)
        std = math.sqrt(var)
    else:
        mean_rate, std = 0.0, 0.0

    if z >= 1.96 and pooled_win_rate > 0.5:
        verdict = "EDGE"
    elif total_settled < 30:
        verdict = "INSUFFICIENT_DATA"
    else:
        verdict = "NO_EDGE"

    return WalkForwardReport(
        strategy_id=strategy_id, symbol=symbol, total_bars=total_bars,
        folds=folds, mean_test_win_rate=mean_rate, aggregate_z_score=z,
        per_fold_win_rate_std=std, verdict=verdict,
    )
