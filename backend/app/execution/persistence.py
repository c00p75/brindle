"""Persists OrderIntent attempts, fills, and materializes positions.

Called by ExecutionService after every adapter response so the platform
keeps a complete trail of what was sent and what came back, plus a
materialized view of current positions for the dashboard.
"""
from __future__ import annotations

from sqlalchemy import select

from app.core.eventbus import get_event_bus
from app.core.ids import new_id
from app.core.time import now_epoch_ms
from app.db.engine import session_scope
from app.db.orm import FillRow, OrderRow, PositionRow
from app.execution.models import (
    ExecutionResult,
    ExecutionStatus,
    OrderIntent,
    Side,
)


def record_attempt(intent: OrderIntent, result: ExecutionResult) -> None:
    """Idempotent on (client_order_id). One row per attempt."""
    bus = get_event_bus()
    ts = now_epoch_ms()

    with session_scope() as s:
        existing = s.get(OrderRow, intent.client_order_id)
        if existing is None:
            row = OrderRow(
                client_order_id=intent.client_order_id,
                bot_id=intent.bot_id,
                strategy_id=intent.strategy_id,
                config_version=intent.config_version,
                adapter_id=result.adapter_id,
                symbol=intent.symbol,
                side=intent.side.value,
                order_type=intent.order_type.value,
                quantity=intent.quantity,
                notional=intent.notional,
                limit_price=intent.limit_price,
                status=result.status.value,
                broker_order_id=result.broker_order_id,
                reason=result.reason,
                submitted_at_ms=ts,
                extra=result.extra or {},
            )
            s.add(row)
        else:
            existing.status = result.status.value
            existing.broker_order_id = result.broker_order_id
            existing.reason = result.reason
            if result.extra:
                existing.extra = result.extra

        # Publish order event
        bus.publish(intent.bot_id, "order", {
            "client_order_id": intent.client_order_id,
            "symbol": intent.symbol,
            "side": intent.side.value,
            "order_type": intent.order_type.value,
            "quantity": intent.quantity,
            "notional": intent.notional,
            "status": result.status.value,
            "reason": result.reason,
            "submitted_at_ms": ts,
        })

        if result.status == ExecutionStatus.FILLED and result.filled_qty and result.avg_price:
            fill_id = new_id("fill")
            fill = FillRow(
                id=fill_id,
                bot_id=intent.bot_id,
                client_order_id=intent.client_order_id,
                symbol=intent.symbol,
                side=intent.side.value,
                quantity=result.filled_qty,
                price=result.avg_price,
                fees=result.fees or 0.0,
                filled_at_ms=ts,
            )
            s.add(fill)

            # Publish fill event
            bus.publish(intent.bot_id, "fill", {
                "id": fill_id,
                "symbol": intent.symbol,
                "side": intent.side.value,
                "quantity": result.filled_qty,
                "price": result.avg_price,
                "fees": result.fees or 0.0,
                "filled_at_ms": ts,
            })

            _apply_fill_to_position(
                s,
                bot_id=intent.bot_id,
                symbol=intent.symbol,
                signed_qty=result.filled_qty if intent.side == Side.BUY else -result.filled_qty,
                price=result.avg_price,
                bus=bus,
            )


def _apply_fill_to_position(s, *, bot_id: str, symbol: str, signed_qty: float, price: float, bus=None) -> None:
    pos = s.get(PositionRow, (bot_id, symbol))
    if pos is None:
        s.add(
            PositionRow(
                bot_id=bot_id,
                symbol=symbol,
                quantity=signed_qty,
                avg_price=price,
                realized_pnl=0.0,
                updated_at_ms=now_epoch_ms(),
            )
        )
        if bus:
            bus.publish(bot_id, "position", {
                "symbol": symbol, "quantity": signed_qty,
                "avg_price": price, "realized_pnl": 0.0,
                "updated_at_ms": now_epoch_ms(),
            })
        return

    new_qty = pos.quantity + signed_qty
    same_dir = (pos.quantity >= 0) == (signed_qty >= 0)

    if pos.quantity == 0:
        pos.avg_price = price
        pos.quantity = signed_qty
    elif new_qty == 0:
        # closed flat: realize PnL on the closed amount
        if pos.avg_price is not None:
            sign = 1 if pos.quantity > 0 else -1
            pos.realized_pnl += sign * (price - pos.avg_price) * abs(pos.quantity)
        pos.quantity = 0.0
        pos.avg_price = None
    elif same_dir:
        # increasing in same direction → weighted-average cost
        if pos.avg_price is None:
            pos.avg_price = price
        else:
            pos.avg_price = (
                abs(pos.quantity) * pos.avg_price + abs(signed_qty) * price
            ) / (abs(pos.quantity) + abs(signed_qty))
        pos.quantity = new_qty
    else:
        # reducing or flipping
        closed = min(abs(pos.quantity), abs(signed_qty))
        sign = 1 if pos.quantity > 0 else -1
        if pos.avg_price is not None:
            pos.realized_pnl += sign * (price - pos.avg_price) * closed
        pos.quantity = new_qty
        if (pos.quantity > 0) == (signed_qty > 0) and abs(pos.quantity) > 0:
            # flipped past zero → new leg opened at this price
            pos.avg_price = price
        elif pos.quantity == 0:
            pos.avg_price = None

    pos.updated_at_ms = now_epoch_ms()

    if bus:
        bus.publish(bot_id, "position", {
            "symbol": symbol, "quantity": pos.quantity,
            "avg_price": pos.avg_price, "realized_pnl": pos.realized_pnl,
            "updated_at_ms": pos.updated_at_ms,
        })


def list_orders(bot_id: str, limit: int = 100) -> list[dict]:
    with session_scope() as s:
        rows = (
            s.execute(
                select(OrderRow)
                .where(OrderRow.bot_id == bot_id)
                .order_by(OrderRow.submitted_at_ms.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_order_dict(r) for r in rows]


def list_fills(bot_id: str, limit: int = 100) -> list[dict]:
    with session_scope() as s:
        rows = (
            s.execute(
                select(FillRow)
                .where(FillRow.bot_id == bot_id)
                .order_by(FillRow.filled_at_ms.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return [_fill_dict(r) for r in rows]


def list_positions(bot_id: str) -> list[dict]:
    with session_scope() as s:
        rows = (
            s.execute(select(PositionRow).where(PositionRow.bot_id == bot_id))
            .scalars()
            .all()
        )
        return [_position_dict(r) for r in rows]


def get_position_qty(bot_id: str, symbol: str) -> float:
    with session_scope() as s:
        pos = s.get(PositionRow, (bot_id, symbol))
        return pos.quantity if pos else 0.0


def _order_dict(r: OrderRow) -> dict:
    return {
        "client_order_id": r.client_order_id,
        "bot_id": r.bot_id,
        "strategy_id": r.strategy_id,
        "config_version": r.config_version,
        "adapter_id": r.adapter_id,
        "symbol": r.symbol,
        "side": r.side,
        "order_type": r.order_type,
        "quantity": r.quantity,
        "notional": r.notional,
        "limit_price": r.limit_price,
        "status": r.status,
        "broker_order_id": r.broker_order_id,
        "reason": r.reason,
        "submitted_at_ms": r.submitted_at_ms,
    }


def _fill_dict(r: FillRow) -> dict:
    return {
        "id": r.id,
        "bot_id": r.bot_id,
        "client_order_id": r.client_order_id,
        "symbol": r.symbol,
        "side": r.side,
        "quantity": r.quantity,
        "price": r.price,
        "fees": r.fees,
        "filled_at_ms": r.filled_at_ms,
    }


def _position_dict(r: PositionRow) -> dict:
    return {
        "bot_id": r.bot_id,
        "symbol": r.symbol,
        "quantity": r.quantity,
        "avg_price": r.avg_price,
        "realized_pnl": r.realized_pnl,
        "updated_at_ms": r.updated_at_ms,
    }
