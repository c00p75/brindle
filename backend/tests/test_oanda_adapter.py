"""Unit tests for OandaAdapter — all network calls are mocked.

No real OANDA credentials or network access required.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.adapters.brokers.base import AdapterHealth, BrokerConfig
from app.adapters.brokers.oanda_adapter import OandaAdapter
from app.execution.models import ExecutionStatus, OrderIntent, OrderType, Side


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config() -> BrokerConfig:
    return BrokerConfig(
        type="oanda",
        environment="practice",
        account_id="001-001-1234567-001",
        credential_ref="secret://env/OANDA_TEST_KEY",
        symbol_namespace="oanda",
    )


def _intent(
    cid: str = "c-1",
    symbol: str = "EUR/USD",
    side: Side = Side.BUY,
    qty: float = 1000.0,
    order_type: OrderType = OrderType.MARKET,
    limit_price: float | None = None,
) -> OrderIntent:
    return OrderIntent(
        bot_id="bot_test",
        strategy_id="trend_v1",
        client_order_id=cid,
        symbol=symbol,
        side=side,
        order_type=order_type,
        quantity=qty,
        limit_price=limit_price,
        config_version=1,
    )


def _resp(status: int, body: dict) -> MagicMock:
    m = MagicMock()
    m.status_code = status
    m.json.return_value = body
    if status >= 400:
        m.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status}", request=MagicMock(), response=m
        )
    else:
        m.raise_for_status.return_value = None
    return m


_ACCOUNT_SUMMARY = {
    "account": {
        "currency": "USD",
        "balance": "100000.00",
        "NAV": "100050.00",
        "marginAvailable": "99000.00",
    }
}


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("OANDA_TEST_KEY", "test-api-key-xyz")


@pytest.fixture
def mock_http():
    """Patch httpx.AsyncClient; return the mock instance."""
    mock_instance = AsyncMock()
    with patch("app.adapters.brokers.oanda_adapter.httpx.AsyncClient") as MockCls:
        MockCls.return_value = mock_instance
        yield mock_instance


async def _connected_adapter(mock_http) -> OandaAdapter:
    mock_http.get.return_value = _resp(200, _ACCOUNT_SUMMARY)
    adapter = OandaAdapter(_config())
    await adapter.connect()
    return adapter


# ---------------------------------------------------------------------------
# connect / close
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_connect_verifies_account(mock_http):
    mock_http.get.return_value = _resp(200, _ACCOUNT_SUMMARY)
    adapter = OandaAdapter(_config())
    await adapter.connect()
    assert adapter._connected
    mock_http.get.assert_called_once()
    call_url = mock_http.get.call_args[0][0]
    assert "summary" in call_url


@pytest.mark.asyncio
async def test_connect_raises_on_401(mock_http):
    mock_http.get.return_value = _resp(401, {"errorMessage": "Unauthorized"})
    adapter = OandaAdapter(_config())
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.connect()
    assert not adapter._connected


@pytest.mark.asyncio
async def test_close_disconnects(mock_http):
    adapter = await _connected_adapter(mock_http)
    await adapter.close()
    assert not adapter._connected
    mock_http.aclose.assert_called_once()


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_health_healthy_when_connected(mock_http):
    adapter = await _connected_adapter(mock_http)
    mock_http.get.return_value = _resp(200, _ACCOUNT_SUMMARY)
    assert await adapter.health_check() == AdapterHealth.HEALTHY


@pytest.mark.asyncio
async def test_health_disconnected_before_connect(mock_http):
    adapter = OandaAdapter(_config())
    assert await adapter.health_check() == AdapterHealth.DISCONNECTED


@pytest.mark.asyncio
async def test_health_error_on_401(mock_http):
    adapter = await _connected_adapter(mock_http)
    mock_http.get.return_value = _resp(401, {})
    assert await adapter.health_check() == AdapterHealth.ERROR


@pytest.mark.asyncio
async def test_health_disconnected_on_network_error(mock_http):
    adapter = await _connected_adapter(mock_http)
    mock_http.get.side_effect = httpx.ConnectError("timeout")
    assert await adapter.health_check() == AdapterHealth.DISCONNECTED


# ---------------------------------------------------------------------------
# get_ticker
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_ticker_returns_bid_ask(mock_http):
    adapter = await _connected_adapter(mock_http)
    mock_http.get.return_value = _resp(200, {
        "prices": [{
            "instrument": "EUR_USD",
            "bids": [{"price": "1.09990", "liquidity": 1_000_000}],
            "asks": [{"price": "1.10010", "liquidity": 1_000_000}],
            "time": "2024-01-01T12:00:00.000000000Z",
            "tradeable": True,
        }]
    })
    ticker = await adapter.get_ticker("EUR/USD")
    assert ticker.symbol == "EUR/USD"
    assert ticker.bid == pytest.approx(1.09990)
    assert ticker.ask == pytest.approx(1.10010)


@pytest.mark.asyncio
async def test_get_ticker_translates_symbol_to_native(mock_http):
    adapter = await _connected_adapter(mock_http)
    mock_http.get.return_value = _resp(200, {
        "prices": [{
            "instrument": "GBP_USD",
            "bids": [{"price": "1.26990"}],
            "asks": [{"price": "1.27010"}],
            "time": "2024-01-01T12:00:00.000000000Z",
        }]
    })
    ticker = await adapter.get_ticker("GBP/USD")
    # verify native symbol was sent in request
    call_kwargs = mock_http.get.call_args
    assert "GBP_USD" in str(call_kwargs)
    assert ticker.symbol == "GBP/USD"


# ---------------------------------------------------------------------------
# get_balance
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_balance(mock_http):
    adapter = await _connected_adapter(mock_http)
    mock_http.get.return_value = _resp(200, _ACCOUNT_SUMMARY)
    balances = await adapter.get_balance()
    assert len(balances) == 1
    assert balances[0].currency == "USD"
    assert balances[0].total == pytest.approx(100050.0)
    assert balances[0].available == pytest.approx(99000.0)


# ---------------------------------------------------------------------------
# get_positions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_positions_long(mock_http):
    adapter = await _connected_adapter(mock_http)
    mock_http.get.return_value = _resp(200, {
        "positions": [{
            "instrument": "EUR_USD",
            "long":  {"units": "10000", "averagePrice": "1.10000", "unrealizedPL": "0"},
            "short": {"units": "0",     "averagePrice": "0",       "unrealizedPL": "0"},
        }]
    })
    positions = await adapter.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "EUR/USD"
    assert positions[0].quantity == pytest.approx(10000.0)
    assert positions[0].avg_price == pytest.approx(1.10)


@pytest.mark.asyncio
async def test_get_positions_skips_flat(mock_http):
    adapter = await _connected_adapter(mock_http)
    mock_http.get.return_value = _resp(200, {
        "positions": [{
            "instrument": "EUR_USD",
            "long":  {"units": "0", "averagePrice": "0", "unrealizedPL": "0"},
            "short": {"units": "0", "averagePrice": "0", "unrealizedPL": "0"},
        }]
    })
    positions = await adapter.get_positions()
    assert positions == []


# ---------------------------------------------------------------------------
# place_order — market fill
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_place_market_buy_fills(mock_http):
    adapter = await _connected_adapter(mock_http)
    mock_http.post.return_value = _resp(201, {
        "orderFillTransaction": {
            "id": "12345",
            "type": "ORDER_FILL",
            "instrument": "EUR_USD",
            "units": "1000",
            "price": "1.10005",
        },
        "relatedTransactionIDs": ["12344", "12345"],
    })
    result = await adapter.place_order(_intent("c-buy", side=Side.BUY, qty=1000))
    assert result.status == ExecutionStatus.FILLED
    assert result.filled_qty == pytest.approx(1000.0)
    assert result.avg_price == pytest.approx(1.10005)
    assert result.broker_order_id == "12345"
    assert result.adapter_id == "oanda"

    # Verify OANDA received positive units for BUY
    body = mock_http.post.call_args[1]["json"]["order"]
    assert float(body["units"]) > 0


@pytest.mark.asyncio
async def test_place_market_sell_fills(mock_http):
    adapter = await _connected_adapter(mock_http)
    mock_http.post.return_value = _resp(201, {
        "orderFillTransaction": {
            "id": "12346",
            "units": "-1000",
            "price": "1.09995",
        },
    })
    result = await adapter.place_order(_intent("c-sell", side=Side.SELL, qty=1000))
    assert result.status == ExecutionStatus.FILLED
    assert result.filled_qty == pytest.approx(1000.0)

    # Verify OANDA received negative units for SELL
    body = mock_http.post.call_args[1]["json"]["order"]
    assert float(body["units"]) < 0


# ---------------------------------------------------------------------------
# place_order — limit accepted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_place_limit_order_accepted(mock_http):
    adapter = await _connected_adapter(mock_http)
    mock_http.post.return_value = _resp(201, {
        "orderCreateTransaction": {
            "id": "99001",
            "type": "LIMIT_ORDER",
            "instrument": "EUR_USD",
            "units": "500",
            "price": "1.09500",
        },
    })
    result = await adapter.place_order(
        _intent("c-lim", order_type=OrderType.LIMIT, qty=500, limit_price=1.095)
    )
    assert result.status == ExecutionStatus.ACCEPTED
    assert result.broker_order_id == "99001"

    body = mock_http.post.call_args[1]["json"]["order"]
    assert body["type"] == "LIMIT"
    assert body["price"] == "1.095"
    assert body["timeInForce"] == "GTC"


# ---------------------------------------------------------------------------
# place_order — rejected by broker
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_place_order_rejected_by_broker(mock_http):
    adapter = await _connected_adapter(mock_http)
    mock_http.post.return_value = _resp(400, {
        "orderRejectTransaction": {
            "type": "MARKET_ORDER_REJECT",
            "rejectReason": "INSUFFICIENT_MARGIN",
        }
    })
    result = await adapter.place_order(_intent("c-rej", qty=999_999))
    assert result.status == ExecutionStatus.REJECTED
    assert "INSUFFICIENT_MARGIN" in (result.reason or "")


# ---------------------------------------------------------------------------
# place_order — not connected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_place_order_not_connected(mock_http):
    adapter = OandaAdapter(_config())  # never connect()
    adapter._client = None
    result = await adapter.place_order(_intent("c-nc"))
    assert result.status == ExecutionStatus.REJECTED
    assert result.reason == "adapter not connected"


# ---------------------------------------------------------------------------
# cancel_order
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cancel_order_success(mock_http):
    adapter = await _connected_adapter(mock_http)
    mock_http.put.return_value = _resp(200, {"orderCancelTransaction": {"id": "12345"}})
    ok = await adapter.cancel_order("12345")
    assert ok is True
    url = mock_http.put.call_args[0][0]
    assert "12345" in url and "cancel" in url


@pytest.mark.asyncio
async def test_cancel_order_not_found(mock_http):
    adapter = await _connected_adapter(mock_http)
    mock_http.put.return_value = _resp(404, {"errorMessage": "Order not found"})
    ok = await adapter.cancel_order("99999")
    assert ok is False


# ---------------------------------------------------------------------------
# Symbol translation
# ---------------------------------------------------------------------------

def test_unknown_symbol_raises():
    adapter = OandaAdapter(_config())
    with pytest.raises(ValueError, match="not mapped"):
        adapter._mapper.to_native("BTC/USD")  # not in OANDA namespace


# ---------------------------------------------------------------------------
# Secrets resolver
# ---------------------------------------------------------------------------

def test_resolver_reads_env(monkeypatch):
    monkeypatch.setenv("MY_SECRET", "hunter2")
    from app.secrets.resolver import resolve
    assert resolve("secret://env/MY_SECRET") == "hunter2"


def test_resolver_paper_sentinel():
    from app.secrets.resolver import resolve
    assert resolve("secret://paper/none") == ""


def test_resolver_missing_env_raises(monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    from app.secrets.resolver import resolve
    with pytest.raises(ValueError, match="MISSING_VAR"):
        resolve("secret://env/MISSING_VAR")


def test_resolver_unknown_scheme_raises():
    from app.secrets.resolver import resolve
    with pytest.raises(ValueError, match="unsupported secret scheme"):
        resolve("vault://secret/foo")
