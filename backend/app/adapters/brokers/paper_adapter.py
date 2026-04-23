"""PaperAdapter — deterministic simulator. Zero network dependency.

Required to exist at all times (see MULTI_ADAPTER_BROKER_SYSTEM.md).
Used as:
- default adapter for research/testing,
- the only adapter allowed to place orders while PAPER_TRADING_ONLY is set.
"""
from __future__ import annotations

import asyncio
from typing import Any

from app.adapters.brokers.base import (
    AdapterHealth,
    Balance,
    BrokerConfig,
    Position,
    Ticker,
)
from app.adapters.symbols.mapping import get_mapper
from app.core.ids import new_id
from app.core.time import now_epoch_ms
from app.execution.models import (
    ExecutionResult,
    ExecutionStatus,
    OrderIntent,
    OrderType,
    Side,
)


class PaperAdapter:
    id = "paper"

    def __init__(self, config: BrokerConfig) -> None:
        self.config = config
        self._connected = False
        self._mapper = get_mapper(config.symbol_namespace)
        self._positions: dict[str, Position] = {}
        self._open_orders: dict[str, dict[str, Any]] = {}
        self._balance = Balance(currency="USD", available=100_000.0, total=100_000.0)
        # Deterministic fake tickers. Replace with injected market data later.
        self._marks: dict[str, float] = {
            "EUR/USD": 1.10,
            "GBP/USD": 1.27,
            "USD/JPY": 148.0,
            "BTC/USD": 60_000.0,
            "BTC/USDT": 60_000.0,
        }

    async def connect(self) -> None:
        await asyncio.sleep(0)
        self._connected = True

    async def close(self) -> None:
        self._connected = False

    async def get_ticker(self, symbol: str) -> Ticker:
        self._mapper.to_native(symbol)  # validates mapping
        mark = self._marks.get(symbol, 1.0)
        spread = mark * 0.0002
        return Ticker(
            symbol=symbol,
            bid=mark - spread / 2,
            ask=mark + spread / 2,
            ts_ms=now_epoch_ms(),
        )

    async def get_balance(self) -> list[Balance]:
        return [self._balance]

    async def get_positions(self) -> list[Position]:
        return list(self._positions.values())

    async def get_open_orders(self) -> list[dict]:
        return list(self._open_orders.values())

    async def place_order(self, intent: OrderIntent) -> ExecutionResult:
        if not self._connected:
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                client_order_id=intent.client_order_id,
                reason="adapter not connected",
                adapter_id=self.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
            )
        ticker = await self.get_ticker(intent.symbol)
        fill_price = ticker.ask if intent.side == Side.BUY else ticker.bid

        if intent.order_type == OrderType.LIMIT and intent.limit_price is not None:
            crosses = (
                (intent.side == Side.BUY and intent.limit_price >= ticker.ask)
                or (intent.side == Side.SELL and intent.limit_price <= ticker.bid)
            )
            if not crosses:
                broker_id = new_id("pord")
                self._open_orders[broker_id] = {
                    "broker_order_id": broker_id,
                    "client_order_id": intent.client_order_id,
                    "symbol": intent.symbol,
                    "side": intent.side.value,
                    "limit_price": intent.limit_price,
                }
                return ExecutionResult(
                    status=ExecutionStatus.ACCEPTED,
                    broker_order_id=broker_id,
                    client_order_id=intent.client_order_id,
                    adapter_id=self.id,
                    bot_id=intent.bot_id,
                    config_version=intent.config_version,
                )
            fill_price = intent.limit_price

        qty = intent.quantity if intent.quantity is not None else (
            (intent.notional or 0.0) / fill_price
        )

        pos = self._positions.get(intent.symbol)
        signed = qty if intent.side == Side.BUY else -qty
        if pos is None:
            self._positions[intent.symbol] = Position(
                symbol=intent.symbol, quantity=signed, avg_price=fill_price
            )
        else:
            new_qty = pos.quantity + signed
            if new_qty == 0:
                self._positions.pop(intent.symbol, None)
            else:
                # Keep avg_price on size-increasing fills; reset on flip.
                same_dir = (pos.quantity > 0) == (new_qty > 0)
                avg = pos.avg_price or fill_price
                if same_dir and abs(new_qty) > abs(pos.quantity):
                    avg = (
                        (abs(pos.quantity) * avg + abs(signed) * fill_price)
                        / abs(new_qty)
                    )
                elif not same_dir:
                    avg = fill_price
                self._positions[intent.symbol] = Position(
                    symbol=intent.symbol, quantity=new_qty, avg_price=avg
                )

        return ExecutionResult(
            status=ExecutionStatus.FILLED,
            broker_order_id=new_id("pord"),
            client_order_id=intent.client_order_id,
            filled_qty=qty,
            avg_price=fill_price,
            fees=0.0,
            adapter_id=self.id,
            bot_id=intent.bot_id,
            config_version=intent.config_version,
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        return self._open_orders.pop(broker_order_id, None) is not None

    async def health_check(self) -> AdapterHealth:
        return AdapterHealth.HEALTHY if self._connected else AdapterHealth.DISCONNECTED
