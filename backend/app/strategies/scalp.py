"""scalp_v1 — micro-move scalper with tight stops.

From quantvps.com (#7 Scalping): "make small profits from price movements
that occur within seconds or minutes... Success hinges on maintaining a
high win rate since the slim profit margins leave little room for error."

This is structurally distinct from the trend/momentum strategies:
  - trend_v1 waits for SMA crossovers (slow, fewer signals)
  - macd_v1 waits for line crossovers (slower)
  - scalp_v1 fires on every micro-move that exceeds a tiny threshold,
    targeting quick exits at fixed take-profit / stop-loss levels.

Mechanics (entry):
  - Compute short-window ATR.
  - If price has moved up by `entry_atr_mult` × ATR over the last
    `lookback` bars: BUY (assumes momentum continues).
  - If down by the same amount: SELL.

Mechanics (exit):
  - Hold until either (1) take-profit threshold hit
    (`tp_atr_mult` × ATR from entry) OR (2) stop-loss
    (`sl_atr_mult` × ATR from entry) OR (3) max hold ticks reached.
  - Position management is internal — the strategy tracks its own entry
    price per symbol and emits exit orders when conditions trigger.

Params:
  lookback:       int   (default 5)
  atr_period:     int   (default 14)
  entry_atr_mult: float (default 0.5) — entry trigger
  tp_atr_mult:    float (default 1.0) — take-profit distance
  sl_atr_mult:    float (default 0.7) — stop-loss distance
  qty:            float (default 1000)
  max_hold_ticks: int   (default 30)
  cooldown_ticks: int   (default 2)
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.ids import new_id
from app.execution.models import OrderIntent, OrderType, Side
from app.strategies.base import StrategyContext
from app.strategies.sizing import make_intent_kwargs


@dataclass
class _ScalpState:
    entry_price: float | None = None
    entry_side: str | None = None  # "buy" | "sell"
    entry_tick: int = 0
    cooldown: int = 0
    tick_count: int = 0


def _wilder(values: list[float], n: int) -> float | None:
    if len(values) < n: return None
    s = sum(values[:n]) / n
    for v in values[n:]:
        s = s - (s / n) + v
    return s


def _true_ranges(bars) -> list[float]:
    out: list[float] = []
    for i in range(1, len(bars)):
        h, l, pc = bars[i].high, bars[i].low, bars[i-1].close
        out.append(max(h - l, abs(h - pc), abs(l - pc)))
    return out


class ScalpV1:
    id = "scalp_v1"

    PARAM_SCHEMA: dict[str, object] = {
        "lookback": 5,
        "atr_period": 14,
        "entry_atr_mult": 0.5,
        "tp_atr_mult": 1.0,
        "sl_atr_mult": 0.7,
        "qty": 1000.0,
        "max_hold_ticks": 30,
        "cooldown_ticks": 2,
    }

    def __init__(self) -> None:
        self._state: dict[str, _ScalpState] = {}

    def _state_for(self, sym: str) -> _ScalpState:
        st = self._state.get(sym)
        if st is None:
            st = _ScalpState()
            self._state[sym] = st
        return st

    def _atr(self, ctx: StrategyContext, atr_n: int) -> float | None:
        bars = [b for b in ctx.bars if b.symbol == ctx.symbol]
        if len(bars) < atr_n + 1:
            return None
        return _wilder(_true_ranges(bars), atr_n)

    def debug_state(self, ctx: StrategyContext) -> dict:
        params = ctx.params
        atr_n = int(params.get("atr_period", 14))
        atr = self._atr(ctx, atr_n)
        st = self._state_for(ctx.symbol)
        cooldown = max(0, int(params.get("cooldown_ticks", 2)) - st.cooldown)
        bars = [b for b in ctx.bars if b.symbol == ctx.symbol]
        if atr is None:
            return {
                "bars_available": len(bars), "bars_needed": atr_n + 1,
                "indicators": {},
                "signal": {
                    "status": "warming_up", "label": "ATR warming",
                    "detail": f"need {atr_n + 1}, have {len(bars)}",
                    "cooldown_remaining": 0,
                },
            }
        if st.entry_price is not None:
            held = st.tick_count - st.entry_tick
            move = ctx.mark_price - st.entry_price
            sign = 1 if st.entry_side == "buy" else -1
            unrealized = sign * move
            status, label = "watching", f"In trade ({st.entry_side}) — {held} ticks"
            detail = f"entry {st.entry_price:.5f}, mark {ctx.mark_price:.5f}, unreal {unrealized:+.5f}"
        elif cooldown > 0:
            status, label = "cooldown", f"Cooldown — {cooldown} tick(s)"
            detail = "Recent exit; waiting."
        else:
            status, label = "watching", "Looking for micro move"
            detail = f"ATR {atr:.5f}"
        return {
            "bars_available": len(bars), "bars_needed": atr_n + 1,
            "indicators": {
                "atr": round(atr, 6),
                "in_position": st.entry_price is not None,
                "entry_price": round(st.entry_price, 6) if st.entry_price else None,
            },
            "signal": {
                "status": status, "label": label, "detail": detail,
                "cooldown_remaining": cooldown,
            },
        }

    def on_data(self, ctx: StrategyContext) -> list[OrderIntent]:
        params = ctx.params
        lookback = int(params.get("lookback", 5))
        atr_n = int(params.get("atr_period", 14))
        entry_mult = float(params.get("entry_atr_mult", 0.5))
        tp_mult = float(params.get("tp_atr_mult", 1.0))
        sl_mult = float(params.get("sl_atr_mult", 0.7))
        qty = float(params.get("qty", 1000))
        max_hold = int(params.get("max_hold_ticks", 30))
        cooldown_ticks = int(params.get("cooldown_ticks", 2))

        st = self._state_for(ctx.symbol)
        st.tick_count += 1
        atr = self._atr(ctx, atr_n)
        if atr is None or atr == 0:
            return []

        sizing = make_intent_kwargs(ctx, qty)
        if sizing is None:
            return []

        # Exit logic — managing an open position
        if st.entry_price is not None:
            held = st.tick_count - st.entry_tick
            move = ctx.mark_price - st.entry_price
            sign = 1 if st.entry_side == "buy" else -1
            pnl = sign * move
            should_exit = (
                pnl >= tp_mult * atr or pnl <= -sl_mult * atr or held >= max_hold
            )
            if should_exit:
                exit_side = Side.SELL if st.entry_side == "buy" else Side.BUY
                # Reset state — cooldown begins
                st.entry_price = None
                st.entry_side = None
                st.entry_tick = 0
                st.cooldown = 0
                return [OrderIntent(
                    bot_id=ctx.bot_id, strategy_id=ctx.strategy_id,
                    client_order_id=new_id("coid"), symbol=ctx.symbol,
                    side=exit_side, order_type=OrderType.MARKET,
                    config_version=ctx.config_version,
                    **sizing,
                )]
            return []

        # Entry logic — flat position
        st.cooldown += 1
        if st.cooldown < cooldown_ticks:
            return []

        bars = [b for b in ctx.bars if b.symbol == ctx.symbol]
        if len(bars) <= lookback:
            return []
        recent_move = bars[-1].close - bars[-1 - lookback].close
        if recent_move >= entry_mult * atr:
            st.entry_price = ctx.mark_price
            st.entry_side = "buy"
            st.entry_tick = st.tick_count
            st.cooldown = 0
            return [OrderIntent(
                bot_id=ctx.bot_id, strategy_id=ctx.strategy_id,
                client_order_id=new_id("coid"), symbol=ctx.symbol,
                side=Side.BUY, order_type=OrderType.MARKET,
                config_version=ctx.config_version,
                **sizing,
            )]
        if recent_move <= -entry_mult * atr:
            st.entry_price = ctx.mark_price
            st.entry_side = "sell"
            st.entry_tick = st.tick_count
            st.cooldown = 0
            return [OrderIntent(
                bot_id=ctx.bot_id, strategy_id=ctx.strategy_id,
                client_order_id=new_id("coid"), symbol=ctx.symbol,
                side=Side.SELL, order_type=OrderType.MARKET,
                config_version=ctx.config_version,
                **sizing,
            )]
        return []
