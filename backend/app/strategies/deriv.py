"""deriv_v1 — Deriv-native momentum strategy (SMA + RSI).

Designed for binary options / digital contracts on Deriv. Uses `notional`
(USD stake) instead of `quantity`, does NOT track or flip positions,
and enforces a cooldown between trades to avoid over-trading on short-
duration contracts.

Signal logic:
  - Computes a fast SMA and an RSI on the close prices.
  - BUY (→ CALL contract): RSI crosses above `rsi_oversold` AND price is
    above the SMA (momentum confirms direction).
  - SELL (→ PUT contract): RSI crosses below `rsi_overbought` AND price
    is below the SMA.
  - Cooldown: after any signal, suppress for `cooldown_ticks` ticks to
    let the contract play out before entering another.

Params:
  sma_period:     int   (default 14) — SMA lookback
  rsi_period:     int   (default 14) — RSI lookback
  rsi_overbought: float (default 70) — overbought threshold
  rsi_oversold:   float (default 30) — oversold threshold
  stake:          float (default 10) — USD per contract
  cooldown_ticks: int   (default 60) — ticks to wait between trades
"""
from __future__ import annotations

from app.core.ids import new_id
from app.execution.models import OrderIntent, OrderType, Side
from app.strategies.base import StrategyContext


def _sma(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def _rsi(values: list[float], n: int) -> float | None:
    """Wilder's RSI. Returns None when there aren't enough bars."""
    if len(values) < n + 1:
        return None

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    # Seed with simple average of first `n` periods
    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n

    # Smooth subsequent periods (Wilder)
    for i in range(n, len(gains)):
        avg_gain = (avg_gain * (n - 1) + gains[i]) / n
        avg_loss = (avg_loss * (n - 1) + losses[i]) / n

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class DerivV1:
    """Deriv-native SMA + RSI momentum strategy."""

    id = "deriv_v1"

    def __init__(self) -> None:
        # Per-symbol tick counter since last trade (cooldown tracking).
        self._ticks_since_trade: dict[str, int] = {}
        # Previous RSI value per symbol for crossover detection.
        self._prev_rsi: dict[str, float | None] = {}

    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]:
        params = ctx.params
        sma_period = int(params.get("sma_period", 14))
        rsi_period = int(params.get("rsi_period", 14))
        rsi_overbought = float(params.get("rsi_overbought", 70))
        rsi_oversold = float(params.get("rsi_oversold", 30))
        stake = float(params.get("stake", 10.0))
        cooldown_ticks = int(params.get("cooldown_ticks", 60))

        if sma_period <= 0 or rsi_period <= 0 or stake <= 0:
            return []

        closes = [b.close for b in ctx.bars if b.symbol == ctx.symbol]
        min_bars = max(sma_period, rsi_period + 1)
        if len(closes) < min_bars:
            return []

        sma_val = _sma(closes, sma_period)
        rsi_val = _rsi(closes, rsi_period)
        prev_rsi = self._prev_rsi.get(ctx.symbol)
        self._prev_rsi[ctx.symbol] = rsi_val

        if sma_val is None or rsi_val is None:
            return []

        # Track cooldown
        ticks = self._ticks_since_trade.get(ctx.symbol, cooldown_ticks)
        self._ticks_since_trade[ctx.symbol] = ticks + 1

        if ticks < cooldown_ticks:
            return []  # still in cooldown

        price = closes[-1]
        intents: list[OrderIntent] = []

        # Bullish: RSI crosses UP through oversold AND price above SMA
        if (
            prev_rsi is not None
            and prev_rsi <= rsi_oversold
            and rsi_val > rsi_oversold
            and price > sma_val
        ):
            intents.append(self._intent(ctx, Side.BUY, stake))
            self._ticks_since_trade[ctx.symbol] = 0

        # Bearish: RSI crosses DOWN through overbought AND price below SMA
        elif (
            prev_rsi is not None
            and prev_rsi >= rsi_overbought
            and rsi_val < rsi_overbought
            and price < sma_val
        ):
            intents.append(self._intent(ctx, Side.SELL, stake))
            self._ticks_since_trade[ctx.symbol] = 0

        return intents

    @staticmethod
    def _intent(ctx: StrategyContext, side: Side, stake: float) -> OrderIntent:
        return OrderIntent(
            bot_id=ctx.bot_id,
            strategy_id=ctx.strategy_id,
            client_order_id=new_id("coid"),
            symbol=ctx.symbol,
            side=side,
            order_type=OrderType.MARKET,
            notional=stake,
            config_version=ctx.config_version,
        )
