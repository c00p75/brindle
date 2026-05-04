"""Unit tests for DerivAdapter — fully offline (HTTP+WebSocket mocked)."""
from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.brokers.base import AdapterHealth, BrokerConfig
from app.adapters.brokers.deriv_adapter import DerivAdapter
from app.execution.models import ExecutionStatus, OrderIntent, OrderType, Side


@contextmanager
def fake_connect(ws):
    """Patch both the OTP fetch and websockets.connect for a unit test."""
    with patch.object(DerivAdapter, "_fetch_otp_url", AsyncMock(return_value="wss://fake/url")), \
         patch("websockets.connect", return_value=ws):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config(**extra_fields) -> BrokerConfig:
    return BrokerConfig(
        type="deriv",
        environment="demo",
        account_id="demo-123",
        credential_ref="secret://paper/none",  # resolves to ""
        symbol_namespace="deriv",
        app_id="1089",
        extra=extra_fields,
    )


def make_intent(side: Side = Side.BUY, notional: float = 10.0) -> OrderIntent:
    return OrderIntent(
        bot_id="bot-1",
        strategy_id="trend",
        client_order_id="ord-001",
        symbol="EUR/USD",
        side=side,
        order_type=OrderType.MARKET,
        notional=notional,
        config_version=1,
    )


class FakeWS:
    """Minimal WebSocket double that returns pre-loaded responses in order."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self._sent: list[dict] = []
        self._queue = asyncio.Queue()
        self.closed = False

    async def send(self, data: str) -> None:
        msg = json.loads(data)
        self._sent.append(msg)
        if self._responses:
            resp = self._responses.pop(0)
            if "req_id" in msg:
                resp["req_id"] = msg["req_id"]
            await self._queue.put(json.dumps(resp))

    async def close(self) -> None:
        self.closed = True
        await self._queue.put(None) # Signal termination

    def __await__(self):
        async def _ret():
            return self
        return _ret().__await__()

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self._queue.get()
        if item is None or self.closed:
            raise StopAsyncIteration
        return item


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def adapter() -> DerivAdapter:
    return DerivAdapter(make_config())


# ---------------------------------------------------------------------------
# connect / close
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_success(adapter):
    ws = FakeWS([])  # no authorize step in new flow

    with fake_connect(ws):
        await adapter.connect()

    assert adapter._connected is True
    await adapter.close()


@pytest.mark.asyncio
async def test_connect_otp_failure(adapter):
    """OTP fetch is the new auth gate; HTTP failure surfaces as ConnectionError."""
    with patch.object(
        DerivAdapter,
        "_fetch_otp_url",
        AsyncMock(side_effect=ConnectionError("Deriv OTP fetch failed (401): InvalidToken")),
    ):
        with pytest.raises(ConnectionError, match="OTP fetch failed"):
            await adapter.connect()

    assert adapter._connected is False


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_check_healthy(adapter):
    ws = FakeWS([{"ping": "pong"}])

    with fake_connect(ws):
        await adapter.connect()
        health = await adapter.health_check()

    assert health == AdapterHealth.HEALTHY
    await adapter.close()


@pytest.mark.asyncio
async def test_health_check_disconnected(adapter):
    health = await adapter.health_check()
    assert health == AdapterHealth.DISCONNECTED


# ---------------------------------------------------------------------------
# get_ticker
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_ticker(adapter):
    ws = FakeWS([{"history": {"prices": [1.1055], "times": [1700000000]}}])

    with fake_connect(ws):
        await adapter.connect()
        ticker = await adapter.get_ticker("EUR/USD")

    assert ticker.symbol == "EUR/USD"
    assert ticker.bid == pytest.approx(1.1055)
    assert ticker.ask == pytest.approx(1.1055)
    await adapter.close()


@pytest.mark.asyncio
async def test_get_ticker_error(adapter):
    ws = FakeWS([{"error": {"message": "InvalidSymbol"}}])

    with fake_connect(ws):
        await adapter.connect()
        with pytest.raises(ValueError, match="InvalidSymbol"):
            await adapter.get_ticker("EUR/USD")
    await adapter.close()


# ---------------------------------------------------------------------------
# get_balance
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_balance(adapter):
    ws = FakeWS([{"balance": {"balance": 500.0, "currency": "USD"}}])

    with fake_connect(ws):
        await adapter.connect()
        balances = await adapter.get_balance()

    assert len(balances) == 1
    assert balances[0].currency == "USD"
    assert balances[0].total == pytest.approx(500.0)
    await adapter.close()


# ---------------------------------------------------------------------------
# place_order — FILLED path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_place_order_filled(adapter):
    ws = FakeWS([
        {"proposal": {"id": "prop-abc", "ask_price": 9.87}},
        {"buy": {"contract_id": 99999, "buy_price": 9.87}},
    ])

    with fake_connect(ws):
        await adapter.connect()
        result = await adapter.place_order(make_intent(Side.BUY))

    assert result.status == ExecutionStatus.FILLED
    assert result.broker_order_id == "99999"
    assert result.avg_price == pytest.approx(9.87)
    await adapter.close()


@pytest.mark.asyncio
async def test_place_order_put_on_sell(adapter):
    """SELL intent should produce a PUT contract proposal."""
    ws = FakeWS([
        {"proposal": {"id": "prop-put", "ask_price": 8.0}},
        {"buy": {"contract_id": 88888, "buy_price": 8.0}},
    ])

    with fake_connect(ws):
        await adapter.connect()
        result = await adapter.place_order(make_intent(Side.SELL))

    assert result.status == ExecutionStatus.FILLED
    # Verify the proposal request contained PUT
    sent_messages = ws._sent
    proposal_msg = next(m for m in sent_messages if "proposal" in m)
    assert proposal_msg["contract_type"] == "PUT"
    await adapter.close()


@pytest.mark.asyncio
async def test_place_order_rejected_by_proposal(adapter):
    ws = FakeWS([{"error": {"message": "ContractBuyValidationError"}}])

    with fake_connect(ws):
        await adapter.connect()
        result = await adapter.place_order(make_intent())

    assert result.status == ExecutionStatus.REJECTED
    assert "ContractBuyValidationError" in (result.reason or "")
    await adapter.close()


@pytest.mark.asyncio
async def test_place_order_not_connected(adapter):
    result = await adapter.place_order(make_intent())
    assert result.status == ExecutionStatus.REJECTED
    assert result.reason == "adapter not connected"


# ---------------------------------------------------------------------------
# cancel_order
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_order_success(adapter):
    ws = FakeWS([{"sell": {"sold_for": 4.5}}])

    with fake_connect(ws):
        await adapter.connect()
        ok = await adapter.cancel_order("99999")

    assert ok is True
    await adapter.close()


@pytest.mark.asyncio
async def test_cancel_order_not_connected(adapter):
    ok = await adapter.cancel_order("12345")
    assert ok is False


# ---------------------------------------------------------------------------
# symbol namespace
# ---------------------------------------------------------------------------

def test_deriv_symbol_mapping():
    from app.adapters.symbols.mapping import DERIV_NAMESPACE

    assert DERIV_NAMESPACE.to_native("EUR/USD") == "frxEURUSD"
    assert DERIV_NAMESPACE.to_native("V75/USD") == "1HZ75V"
    assert DERIV_NAMESPACE.to_native("V100/USD") == "1HZ100V"
    assert DERIV_NAMESPACE.to_native("BOOM1000/USD") == "BOOM1000"
    assert DERIV_NAMESPACE.to_canonical("frxGBPUSD") == "GBP/USD"


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------

def test_deriv_in_registry():
    from app.adapters.brokers.registry import ADAPTER_REGISTRY, list_adapters

    assert "deriv" in ADAPTER_REGISTRY
    assert "deriv" in list_adapters()


def test_factory_creates_deriv():
    from app.adapters.brokers.factory import create_adapter

    cfg = make_config()
    adapter = create_adapter(cfg)
    assert adapter.id == "deriv"
