"""Shared sizing logic for strategies.

All strategies need to decide whether to emit `notional` (USD stake, for
Deriv binary options) or `quantity` (units of asset, for traditional
brokers). This module centralises that decision.

Detection: if the bot has an `allocation` set, it's a Deriv-style
tournament bot and should use notional-based sizing.
"""
from __future__ import annotations

from app.strategies.base import StrategyContext


def compute_stake(ctx: StrategyContext, default_qty: float) -> tuple[float | None, float | None]:
    """Return (quantity, notional) — exactly one will be set, the other None.

    For allocation-based bots (Deriv binary options):
      - If risk_per_trade_pct is configured: notional = balance × pct / 100
      - Else: notional = default_qty (treated as USD stake)
      - Minimum notional: $0.35 (Deriv minimum)

    For traditional bots (no allocation):
      - If risk_per_trade_pct is configured: quantity = (balance × pct / 100) / price
      - Else: quantity = default_qty (treated as units)
    """
    is_deriv = ctx.allocation is not None

    if is_deriv:
        # Notional-based sizing for binary options
        if ctx.risk_per_trade_pct is not None and ctx.effective_balance > 0:
            stake = (ctx.effective_balance * ctx.risk_per_trade_pct) / 100.0
        else:
            stake = default_qty

        # Explicit max_stake cap from risk config
        max_stake = getattr(ctx, "max_stake", None)
        if max_stake is not None:
            stake = min(stake, max_stake)

        # Hard safety cap: stake can never exceed 10% of base allocation,
        # regardless of effective_balance. Prevents runaway sizing if P&L
        # accounting ever over-reports gains.
        if ctx.allocation is not None:
            stake = min(stake, ctx.allocation * 0.10)

        stake = max(stake, 0.35)  # Deriv minimum
        return None, stake

    # Quantity-based sizing for traditional brokers
    if ctx.risk_per_trade_pct is not None and ctx.effective_balance > 0 and ctx.mark_price > 0:
        qty = (ctx.effective_balance * ctx.risk_per_trade_pct / 100.0) / ctx.mark_price
    else:
        qty = default_qty
    if qty <= 0:
        return None, None
    return qty, None


def make_intent_kwargs(ctx: StrategyContext, default_qty: float) -> dict | None:
    """Return kwargs dict with either quantity or notional set, or None if sizing fails.

    Usage in strategies:
        kwargs = make_intent_kwargs(ctx, qty)
        if kwargs is None:
            return []
        return [OrderIntent(..., **kwargs, ...)]
    """
    quantity, notional = compute_stake(ctx, default_qty)
    if quantity is None and notional is None:
        return None
    return {"quantity": quantity, "notional": notional}
