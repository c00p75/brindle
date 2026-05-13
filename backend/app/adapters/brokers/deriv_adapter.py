"""Deriv broker adapter — new api.derivws.com platform, demo only.

Authentication flow (new Deriv API):
  1. POST /trading/v1/options/accounts/{account_id}/otp
       Headers: Deriv-App-ID, Authorization: Bearer <PAT>
  2. Response: { url: "wss://api.derivws.com/trading/v1/options/ws/demo?otp=..." }
  3. Connect directly to that URL — already authenticated, no `authorize`
     payload required.

Credentials:
  - DERIV_APP_ID  — alphanumeric app id from api.deriv.com Registered Apps
  - DERIV_API_TOKEN — Personal Access Token (pat_...) from api.deriv.com
  - account_id    — per-account, e.g. "DOT91022417" (lives in BrokerConfig)

Trade execution:
  proposal (underlying_symbol, contract_type, …) → priced contract
  buy (proposal_id, price)                       → contract opened

BUY intent  → CALL contract (price goes up)
SELL intent → PUT contract  (price goes down)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

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
    Side,
)

log = logging.getLogger("adapter.deriv")

_OTP_BASE = "https://api.derivws.com"
_REQUEST_TIMEOUT = 15.0
_PING_INTERVAL = 25  # seconds — Deriv drops idle connections after ~60 s


class DerivAdapter:
    id = "deriv"

    def __init__(self, config: BrokerConfig) -> None:
        import os

        from app.secrets.resolver import resolve

        self.config = config
        self._api_key = resolve(config.credential_ref)
        self._account_id = config.account_id
        # Resolution order: explicit config > DERIV_APP_ID env > public default 1089.
        self._app_id = config.app_id or os.environ.get("DERIV_APP_ID") or "1089"
        # Default contract duration from BrokerConfig.extra, e.g. {"duration": 5, "duration_unit": "m"}
        self._default_duration: int = int(config.extra.get("duration", 5))
        self._default_duration_unit: str = str(config.extra.get("duration_unit", "m"))
        self._mapper = get_mapper(config.symbol_namespace)
        self._ws: Any = None
        self._connected = False
        self._pending: dict[int, asyncio.Future[dict]] = {}
        self._req_counter = 0
        self._recv_task: asyncio.Task | None = None
        self._tickers: dict[str, Ticker] = {}
        self._subscriptions: set[str] = set()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_otp_url(self) -> str:
        """Exchange (PAT, account_id) for an OTP-authenticated WebSocket URL."""
        path = f"/trading/v1/options/accounts/{self._account_id}/otp"
        headers = {
            "Deriv-App-ID": self._app_id,
            "Authorization": f"Bearer {self._api_key}",
        }
        async with httpx.AsyncClient(base_url=_OTP_BASE, timeout=_REQUEST_TIMEOUT) as c:
            resp = await c.post(path, headers=headers)
        
        if resp.status_code == 404:
            raise ConnectionError(f"Deriv Account Not Found ({self._account_id}). Please check your Account ID in Broker Config.")
        if resp.status_code == 401:
            raise ConnectionError("Deriv Authentication Failed. Please check your Personal Access Token (PAT).")
        if resp.status_code != 200:
            raise ConnectionError(
                f"Deriv OTP fetch failed ({resp.status_code}): {resp.text[:200]}"
            )
        url = resp.json().get("data", {}).get("url")
        if not url:
            raise ConnectionError(
                f"Deriv OTP response missing url field: {resp.text[:200]}"
            )
        return url

    def _next_req_id(self) -> int:
        self._req_counter += 1
        return self._req_counter

    async def _recv_loop(self) -> None:
        """Dispatch incoming WebSocket frames to waiting _send() futures."""
        try:
            async for raw in self._ws:
                try:
                    msg: dict = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                req_id = msg.get("req_id")
                if req_id is not None:
                    fut = self._pending.pop(req_id, None)
                    if fut is not None and not fut.done():
                        fut.set_result(msg)
                
                # Handle incoming ticks from subscriptions
                if "tick" in msg:
                    t = msg["tick"]
                    native = t.get("symbol", "")
                    try:
                        symbol = self._mapper.to_canonical(native)
                    except ValueError:
                        symbol = native
                    price = float(t.get("quote", 0))
                    self._tickers[symbol] = Ticker(
                        symbol=symbol, bid=price, ask=price, 
                        ts_ms=int(t.get("epoch", 0)) * 1000 or now_epoch_ms()
                    )
        except (ConnectionClosed, Exception) as exc:
            log.warning("deriv recv_loop ended: %s", exc)
            self._connected = False
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_exception(ConnectionError(f"connection lost: {exc}"))
            self._pending.clear()

    async def _ensure_connected(self) -> None:
        """Reconnect if the WS dropped. Idempotent — safe to call before any send."""
        if self._connected and self._ws is not None:
            return
        log.info("deriv reconnecting account=%s", self._account_id)
        backoff = 1.0
        for attempt in range(5):
            try:
                await self.connect()
                return
            except Exception as e:  # noqa: BLE001
                log.warning("deriv reconnect attempt %d failed: %s", attempt + 1, e)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15.0)
        raise ConnectionError("deriv reconnect failed after 5 attempts")

    async def _send(self, payload: dict) -> dict:
        """Send a request and await its response by req_id. Auto-reconnects on drop."""
        await self._ensure_connected()
        if self._ws is None:
            raise ConnectionError("adapter not connected")
        req_id = self._next_req_id()
        payload["req_id"] = req_id
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[dict] = loop.create_future()
        self._pending[req_id] = fut
        try:
            await self._ws.send(json.dumps(payload))
            return await asyncio.wait_for(fut, timeout=_REQUEST_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise TimeoutError(f"Deriv request timed out (req_id={req_id}, type={list(payload.keys())})")
        except Exception:
            self._pending.pop(req_id, None)
            raise

    async def connect(self) -> None:
        ws_url = await self._fetch_otp_url()
        self._ws = await websockets.connect(
            ws_url,
            ping_interval=_PING_INTERVAL,
            ping_timeout=10,
            open_timeout=15,
        )
        self._recv_task = asyncio.create_task(self._recv_loop())
        self._connected = True
        log.info(
            "deriv connected account=%s env=%s app_id=%s",
            self._account_id, self.config.environment, self._app_id,
        )
        
        # Re-subscribe to all active symbols after a reconnection
        if self._subscriptions:
            log.info("re-subscribing to %d symbols for account=%s", len(self._subscriptions), self._account_id)
            for symbol in self._subscriptions:
                native = self._mapper.to_native(symbol)
                # Use _send which handles its own req_id and awaiting
                asyncio.create_task(self._send({"ticks": native, "subscribe": 1}))

    async def close(self) -> None:
        self._connected = False
        if self._recv_task is not None:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except (asyncio.CancelledError, Exception):
                pass
            self._recv_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_exception(ConnectionError("adapter closed"))
        self._pending.clear()

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def health_check(self) -> AdapterHealth:
        if not self._connected or self._ws is None:
            return AdapterHealth.DISCONNECTED
        try:
            resp = await self._send({"ping": 1})
            return AdapterHealth.HEALTHY if resp.get("ping") == "pong" else AdapterHealth.DEGRADED
        except TimeoutError:
            return AdapterHealth.DEGRADED
        except Exception:
            return AdapterHealth.DISCONNECTED

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    async def get_ticker(self, symbol: str) -> Ticker:
        native = self._mapper.to_native(symbol)
        
        # If not subscribed yet, send a subscription request
        if symbol not in self._subscriptions:
            log.info("subscribing to deriv ticks for %s", symbol)
            # We don't await the response here to avoid blocking; 
            # the recv_loop will pick up the subscription confirmation and ticks.
            asyncio.create_task(self._send({"ticks": native, "subscribe": 1}))
            self._subscriptions.add(symbol)
            
            # Since we just subscribed, we might not have a ticker yet.
            # Do a one-time poll to seed the cache so the strategy doesn't wait.
            resp = await self._send({
                "ticks_history": native,
                "count": 1,
                "end": "latest",
                "style": "ticks",
            })
            if "history" in resp and resp["history"].get("prices"):
                price = float(resp["history"]["prices"][-1])
                self._tickers[symbol] = Ticker(symbol=symbol, bid=price, ask=price, ts_ms=now_epoch_ms())

        if symbol in self._tickers:
            return self._tickers[symbol]
        
        raise ValueError(f"no tick data available for {symbol!r}")

    async def get_history(self, symbol: str, count: int) -> list[Ticker]:
        native = self._mapper.to_native(symbol)
        resp = await self._send({
            "ticks_history": native,
            "count": count,
            "end": "latest",
            "style": "ticks",
        })
        if "error" in resp:
            raise ValueError(f"deriv get_history error: {resp['error']['message']}")
        
        history = resp.get("history", {})
        prices = history.get("prices", [])
        times = history.get("times", [])
        
        out: list[Ticker] = []
        for p, t in zip(prices, times):
            out.append(Ticker(
                symbol=symbol,
                bid=float(p),
                ask=float(p),
                ts_ms=int(t) * 1000
            ))
        return out

    # ------------------------------------------------------------------
    # Account state
    # ------------------------------------------------------------------

    async def get_balance(self) -> list[Balance]:
        resp = await self._send({"balance": 1})
        if "error" in resp:
            raise ValueError(f"deriv get_balance error: {resp['error']['message']}")
        bal = resp.get("balance", {})
        amount = float(bal.get("balance", 0.0))
        return [Balance(
            currency=bal.get("currency", "USD"),
            available=amount,
            total=amount,
        )]

    async def get_positions(self) -> list[Position]:
        """Return open contracts as positions (stake = quantity, buy_price = avg_price)."""
        resp = await self._send({"portfolio": 1})
        if "error" in resp:
            return []
        out: list[Position] = []
        for contract in resp.get("portfolio", {}).get("contracts", []):
            native = contract.get("symbol", "")
            try:
                canonical = self._mapper.to_canonical(native)
            except ValueError:
                canonical = native
            buy_price = float(contract.get("buy_price", 0.0))
            out.append(Position(symbol=canonical, quantity=buy_price, avg_price=buy_price))
        return out

    async def get_open_orders(self) -> list[dict]:
        resp = await self._send({"portfolio": 1})
        if "error" in resp:
            return []
        out: list[dict] = []
        for c in resp.get("portfolio", {}).get("contracts", []):
            native = c.get("symbol", "")
            try:
                canonical = self._mapper.to_canonical(native)
            except ValueError:
                canonical = native
            out.append({
                "broker_order_id": str(c.get("contract_id", "")),
                "symbol": canonical,
                "side": "buy",
                "order_type": c.get("contract_type", "").lower(),
                "units": c.get("buy_price"),
                "price": c.get("buy_price"),
            })
        return out

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def place_order(self, intent: OrderIntent) -> ExecutionResult:
        if not self._connected or self._ws is None:
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                client_order_id=intent.client_order_id,
                reason="adapter not connected",
                adapter_id=self.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
            )

        native = self._mapper.to_native(intent.symbol)
        contract_type = "CALL" if intent.side == Side.BUY else "PUT"
        stake = round(float(intent.notional if intent.notional is not None else (intent.quantity or 10.0)), 2)

        # Step 1: proposal — get a priced contract
        try:
            proposal_resp = await self._send({
                "proposal": 1,
                "amount": stake,
                "basis": "stake",
                "contract_type": contract_type,
                "currency": "USD",
                "duration": self._default_duration,
                "duration_unit": self._default_duration_unit,
                "underlying_symbol": native,
            })
        except Exception as exc:
            log.warning("deriv proposal error symbol=%s err=%s", intent.symbol, exc)
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                client_order_id=intent.client_order_id,
                reason=f"proposal error: {exc}",
                adapter_id=self.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
            )

        if "error" in proposal_resp:
            err_msg = proposal_resp["error"]["message"]
            log.info("deriv proposal rejected symbol=%s reason=%s", intent.symbol, err_msg)
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                client_order_id=intent.client_order_id,
                reason=err_msg,
                adapter_id=self.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
                extra=proposal_resp,
            )

        proposal_id = proposal_resp.get("proposal", {}).get("id")
        if not proposal_id:
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                client_order_id=intent.client_order_id,
                reason="proposal response missing id",
                adapter_id=self.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
                extra=proposal_resp,
            )

        # Step 2: buy — purchase the contract
        try:
            buy_resp = await self._send({"buy": proposal_id, "price": stake})
        except Exception as exc:
            log.warning("deriv buy error symbol=%s err=%s", intent.symbol, exc)
            return ExecutionResult(
                status=ExecutionStatus.ERROR,
                client_order_id=intent.client_order_id,
                reason=f"buy error: {exc}",
                adapter_id=self.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
            )

        if "error" in buy_resp:
            err_msg = buy_resp["error"]["message"]
            log.info("deriv buy rejected symbol=%s reason=%s", intent.symbol, err_msg)
            return ExecutionResult(
                status=ExecutionStatus.REJECTED,
                client_order_id=intent.client_order_id,
                reason=err_msg,
                adapter_id=self.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
                extra=buy_resp,
            )

        buy_data = buy_resp.get("buy", {})
        contract_id = buy_data.get("contract_id")
        if contract_id:
            buy_price = float(buy_data.get("buy_price", stake))
            payout = float(proposal_resp.get("proposal", {}).get("payout", 0.0))
            expires_at_ms = int(buy_data.get("date_expiry", 0)) * 1000 or None
            log.info(
                "deriv contract bought id=%s symbol=%s stake=%.2f price=%.2f payout=%.2f",
                contract_id, intent.symbol, stake, buy_price, payout,
            )
            from app.execution import contracts as contracts_svc
            try:
                contracts_svc.record_purchase(
                    bot_id=intent.bot_id,
                    contract_id=str(contract_id),
                    client_order_id=intent.client_order_id,
                    symbol=intent.symbol,
                    contract_type=contract_type,
                    stake=stake,
                    expected_payout=payout,
                    purchase_price=buy_price,
                    expires_at_ms=expires_at_ms,
                )
            except Exception as e:  # noqa: BLE001
                log.warning("contract persistence failed id=%s: %s", contract_id, e)
            return ExecutionResult(
                status=ExecutionStatus.FILLED,
                broker_order_id=str(contract_id),
                client_order_id=intent.client_order_id,
                filled_qty=1.0,
                avg_price=buy_price,
                fees=0.0,
                adapter_id=self.id,
                bot_id=intent.bot_id,
                config_version=intent.config_version,
                extra=buy_resp,
            )

        log.warning("deriv unexpected buy response keys=%s", list(buy_resp.keys()))
        return ExecutionResult(
            status=ExecutionStatus.ERROR,
            client_order_id=intent.client_order_id,
            reason=f"unexpected buy response: {list(buy_resp.keys())}",
            adapter_id=self.id,
            bot_id=intent.bot_id,
            config_version=intent.config_version,
            extra=buy_resp,
        )

    async def cancel_order(self, broker_order_id: str) -> bool:
        """Early-exit a binary option contract by selling at market (price=0)."""
        if self._ws is None:
            return False
        try:
            resp = await self._send({"sell": int(broker_order_id), "price": 0})
            return "error" not in resp
        except Exception as exc:
            log.warning("deriv cancel_order error id=%s err=%s", broker_order_id, exc)
            return False

    async def get_contract_status(self, contract_id: str) -> dict | None:
        """Query a contract's current state. Used by runtime to detect settlement.

        Returns a dict with at least:
          { is_sold: bool, status: "open"|"won"|"lost", payout: float, profit: float }
        or None if the request failed.
        """
        if self._ws is None:
            return None
        try:
            resp = await self._send({"proposal_open_contract": 1, "contract_id": int(contract_id)})
        except Exception as exc:
            log.warning("deriv get_contract_status error id=%s err=%s", contract_id, exc)
            return None
        if "error" in resp:
            return None
        c = resp.get("proposal_open_contract", {})
        is_sold = bool(c.get("is_sold", 0))
        if not is_sold:
            return {"is_sold": False, "status": "open", "payout": 0.0, "profit": 0.0}
        # Settled: status is "won" or "lost" per Deriv schema
        return {
            "is_sold": True,
            "status": c.get("status", "lost"),
            "payout": float(c.get("payout", 0.0)),
            "profit": float(c.get("profit", 0.0)),
        }
