"""OANDA v20 REST broker adapter — practice / demo environments only.

Authentication: Bearer token resolved from credential_ref at construction
time via app.secrets.resolver.  The resolved key is held in memory and
never logged or serialised.

Symbol translation: canonical "EUR/USD" <-> OANDA native "EUR_USD" via
the "oanda" SymbolMapper namespace.

Error mapping:
  orderFillTransaction present  → FILLED
  orderCreateTransaction only   → ACCEPTED  (limit resting)
  orderRejectTransaction present → REJECTED
  HTTP 401                       → ERROR (bad credentials)
  network / timeout              → DISCONNECTED
"""
from __future__ import annotations

import logging

import httpx

from app.adapters.brokers.base import (
    AdapterHealth,
    Balance,
    BrokerConfig,
    Position,
    Ticker,
)
from app.adapters.symbols.mapping import get_mapper
from app.core.time import now_epoch_ms
from app.execution.models import (
    ExecutionResult,
    ExecutionStatus,
    OrderIntent,
    OrderType,
    Side,
)

log = logging.getLogger("adapter.oanda")

_PRACTICE_URL = "https://api-fxpractice.oanda.com"


class OandaAdapter:
    id = "oanda"

    def __init__(self, config: BrokerConfig) -> None:
        from app.secrets.resolver import resolve

        self.config = config
        self._api_key = resolve(config.credential_ref)
        self._account_id = config.account_id
        # Both "practice" and "demo" map to the OANDA practice REST endpoint.
        self._base_url = _PRACTICE_URL
        self._mapper = get_mapper(config.symbol_namespace)
        self._client: httpx.AsyncClient | None = None
        self._connected = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        resp = await self._client.get(f"/v3/accounts/{self._account_id}/summary")
        resp.raise_for_status()
        self._connected = True
        log.info("oanda connected account=%s env=%s", self._account_id, self.config.environment)

    async def close(self) -> None:
        self._connected = False
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> AdapterHealth:
        if not self._connected or self._client is None:
            return AdapterHealth.DISCONNECTED
        try:
            resp = await self._client.get(f"/v3/accounts/{self._account_id}/summary")
            if resp.status_code == 200:
                return AdapterHealth.HEALTHY
            if resp.status_code == 401:
                return AdapterHealth.ERROR
            return AdapterHealth.DEGRADED
        except Exception:  # noqa: BLE001
            return AdapterHealth.DISCONNECTED

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_ticker(self, symbol: str) -> Ticker:
        native = self._mapper.to_native(symbol)
        resp = await self._client.get(  # type: ignore[union-attr]
            f"/v3/accounts/{self._account_id}/pricing",
            params={"instruments": native},
        )
        resp.raise_for_status()
        prices = resp.json().get("prices", [])
        if not prices:
            raise ValueError(f"no pricing data returned for {symbol!r}")
        p = prices[0]
        bid = float(p["bids"][0]["price"])
        ask = float(p["asks"][0]["price"])
        return Ticker(symbol=symbol, bid=bid, ask=ask, ts_ms=now_epoch_ms())

    # ------------------------------------------------------------------
    # Account state
    # ------------------------------------------------------------------

    async def get_balance(self) -> list[Balance]:
        resp = await self._client.get(f"/v3/accounts/{self._account_id}/summary")  # type: ignore[union-attr]
        resp.raise_for_status()
        acct = resp.json()["account"]
        return [
            Balance(
                currency=acct["currency"],
                available=float(acct.get("marginAvailable", acct["balance"])),
                total=float(acct["NAV"]),
            )
        ]

    async def get_positions(self) -> list[Position]:
        resp = await self._client.get(  # type: ignore[union-attr]
            f"/v3/accounts/{self._account_id}/openPositions"
        )
        resp.raise_for_status()
        out: list[Position] = []
        for p in resp.json().get("positions", []):
            try:
                canonical = self._mapper.to_canonical(p["instrument"])
            except ValueError:
                continue
            long_qty = float(p["long"]["units"])
            short_qty = float(p["short"]["units"])
            net = long_qty + short_qty
            if net == 0:
                continue
            avg = (
                float(p["long"]["averagePrice"])
                if long_qty > 0
                else float(p["short"]["averagePrice"])
            ) if net != 0 else None
            out.append(Position(symbol=canonical, quantity=net, avg_price=avg))
        return out

    async def get_open_orders(self) -> list[dict]:
        resp = await self._client.get(  # type: ignore[union-attr]
            f"/v3/accounts/{self._account_id}/orders",
            params={"state": "PENDING"},
        )
        resp.raise_for_status()
        out = []
        for o in resp.json().get("orders", []):
            native = o.get("instrument", "")
            try:
                canonical = self._mapper.to_canonical(native)
            except ValueError:
                canonical = native
            units = float(o.get("units", "0"))
            out.append(
                {
                    "broker_order_id": o["id"],
                    "symbol": canonical,
                    "side": "buy" if units > 0 else "sell",
                    "order_type": o.get("type", "").lower().replace("_order", ""),
                    "units": o.get("units"),
                    "price": o.get("price"),
                }
            )
        return out

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def place_order(self, intent: OrderIntent) -> ExecutionResult:
        if not self._connected or self._client is None:
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                client_order_id=intent.client_order_id,
                reason="adapter not connected",
                adapter_id=self.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
            )

        native = self._mapper.to_native(intent.symbol)

        # Resolve quantity: OANDA units are in base currency.
        if intent.quantity is not None:
            qty = intent.quantity
        else:
            ticker = await self.get_ticker(intent.symbol)
            mid = (ticker.bid + ticker.ask) / 2
            qty = (intent.notional or 0.0) / mid

        signed_units = qty if intent.side == Side.BUY else -qty

        order_body: dict = {
            "type": "MARKET" if intent.order_type == OrderType.MARKET else "LIMIT",
            "instrument": native,
            "units": str(signed_units),
        }
        if intent.order_type == OrderType.MARKET:
            order_body["timeInForce"] = "FOK"
        else:
            order_body["price"] = str(intent.limit_price)
            order_body["timeInForce"] = "GTC"

        try:
            resp = await self._client.post(
                f"/v3/accounts/{self._account_id}/orders",
                json={"order": order_body},
            )
            data = resp.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("oanda place_order http error: %s", exc)
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                client_order_id=intent.client_order_id,
                reason=f"http error: {exc}",
                adapter_id=self.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
            )

        if "orderRejectTransaction" in data:
            reason = data["orderRejectTransaction"].get("rejectReason", "rejected by broker")
            log.info("oanda order rejected reason=%s", reason)
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                client_order_id=intent.client_order_id,
                reason=reason,
                adapter_id=self.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
                extra=data,
            )

        if "orderFillTransaction" in data:
            fill = data["orderFillTransaction"]
            filled_qty = abs(float(fill["units"]))
            avg_price = float(fill["price"])
            log.info("oanda order filled qty=%s price=%s", filled_qty, avg_price)
            return ExecutionResult(
                status=ExecutionStatus.FILLED,
                broker_order_id=fill["id"],
                client_order_id=intent.client_order_id,
                filled_qty=filled_qty,
                avg_price=avg_price,
                fees=0.0,
                adapter_id=self.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
                extra=data,
            )

        if "orderCreateTransaction" in data:
            tx = data["orderCreateTransaction"]
            log.info("oanda limit order accepted id=%s", tx["id"])
            return ExecutionResult(
                status=ExecutionStatus.ACCEPTED,
                broker_order_id=tx["id"],
                client_order_id=intent.client_order_id,
                adapter_id=self.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
                extra=data,
            )

        log.warning("oanda unexpected response keys=%s", list(data.keys()))
        return ExecutionResult(
            status=ExecutionStatus.ERROR,
            client_order_id=intent.client_order_id,
            reason=f"unexpected response keys: {list(data.keys())}",
            adapter_id=self.id,
            bot_id=intent.bot_id,
            config_version=intent.config_version,
            extra=data,
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        if self._client is None:
            return False
        resp = await self._client.put(
            f"/v3/accounts/{self._account_id}/orders/{broker_order_id}/cancel"
        )
        return resp.status_code == 200
