import os
from dotenv import load_dotenv

load_dotenv()

import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.alerts.routes import router as alerts_router
from app.alerts.telegram_webhook import router as telegram_router
from app.chat.routes import router as chat_router
from app.audit.routes import router as audit_router
from app.auth.routes import router as auth_router
from app.research.routes import router as research_router
from app.auth.service import seed_default_users
from app.bots.routes import router as bots_router
from app.configs.routes import router as configs_router
from app.llm.routes import router as llm_router
from app.brokers.routes import router as brokers_router
from app.core.logging_config import configure_logging
from app.core.metrics import bots_running, http_request_duration_seconds, http_requests_total
from app.core.settings import get_settings
from app.db.engine import init_db
from app.runtime.manager import get_runtime_manager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    init_db()
    seed_default_users()
    await _resume_running_bots()
    monitor_task = asyncio.create_task(_health_monitor())
    reporter_task = asyncio.create_task(_performance_reporter())
    yield
    monitor_task.cancel()
    reporter_task.cancel()
    try:
        await asyncio.gather(monitor_task, reporter_task, return_exceptions=True)
    except asyncio.CancelledError:
        pass
    await get_runtime_manager().stop_all()


async def _health_monitor() -> None:
    """Background task that emits a CRITICAL alert when running bots drop unexpectedly.

    - Waits 30 s after startup so bots have time to connect.
    - Checks every 60 s.
    - Debounces: only re-alerts when the set of down-bots changes OR 10 minutes
      have passed since the last alert for the same set.
    - Clears debounce state when all expected bots recover.
    """
    import logging
    from app.alerts.models import Severity
    from app.alerts.service import emit
    from app.bots.models import BotState
    from app.bots.service import list_bots

    log = logging.getLogger("health_monitor")
    _RECHECK_INTERVAL = 60          # seconds between ticks
    _STARTUP_DELAY   = 30           # seconds to wait before first check
    _REPEAT_INTERVAL = 10 * 60      # seconds before re-alerting the same set

    last_alerted_ids: frozenset[str] = frozenset()
    last_alert_time: float = 0.0

    await asyncio.sleep(_STARTUP_DELAY)

    while True:
        try:
            mgr = get_runtime_manager()
            actual_ids: set[str] = mgr.running_ids()

            expected_ids: set[str] = {
                bot.id for bot in list_bots() if bot.state == BotState.RUNNING
            }

            missing_ids = expected_ids - actual_ids

            if missing_ids:
                now = asyncio.get_event_loop().time()
                missing_frozen = frozenset(missing_ids)
                new_bots_down  = missing_frozen - last_alerted_ids
                time_elapsed   = now - last_alert_time

                should_alert = bool(new_bots_down) or (time_elapsed >= _REPEAT_INTERVAL)

                if should_alert:
                    expected = len(expected_ids)
                    actual   = len(actual_ids)
                    missing_list = sorted(missing_ids)

                    log.warning(
                        "health_monitor: %d/%d expected bots are down: %s",
                        len(missing_ids), expected, missing_list,
                    )

                    emit(
                        severity=Severity.CRITICAL,
                        source="health_monitor",
                        message=(
                            f"{len(missing_ids)} of {expected} expected bots are not running: "
                            + ", ".join(missing_list)
                        ),
                        metadata={
                            "expected": expected,
                            "actual": actual,
                            "missing_bot_ids": missing_list,
                        },
                    )

                    last_alerted_ids = missing_frozen
                    last_alert_time  = now
            else:
                # All bots recovered — reset debounce state.
                if last_alerted_ids:
                    log.info("health_monitor: all expected bots are running again")
                last_alerted_ids = frozenset()
                last_alert_time  = 0.0

        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("health_monitor: unexpected error during check")

        await asyncio.sleep(_RECHECK_INTERVAL)


async def _performance_reporter() -> None:
    """Send a bot performance summary to Telegram at 06:00, 12:00, and 18:00 UTC.

    Each report covers activity since 00:00 UTC today, so all three reports
    for a given day show cumulative daily progress.  Timezone can be shifted
    by setting REPORT_UTC_OFFSET_HOURS (e.g. 1 for UTC+1).
    """
    import logging
    from datetime import datetime, timezone, timedelta

    from app.alerts import telegram
    from app.bots.models import BotState
    from app.bots.service import list_bots
    from app.configs import service as config_service
    from app.execution import contracts as contracts_svc

    log = logging.getLogger("performance_reporter")

    # Report times as hours in UTC (offset-adjusted if configured)
    tz_offset = int(os.environ.get("REPORT_UTC_OFFSET_HOURS", "0"))
    # User-facing report hours in their local time; we convert to UTC fire times
    LOCAL_HOURS = (6, 12, 18)
    FIRE_HOURS_UTC = tuple((h - tz_offset) % 24 for h in LOCAL_HOURS)
    LABEL = {6: "Morning", 12: "Midday", 18: "Evening"}

    def _seconds_until_next_fire() -> float:
        now_utc = datetime.now(timezone.utc)
        today = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        candidates = [today.replace(hour=h) for h in FIRE_HOURS_UTC]
        future = [c for c in candidates if c > now_utc]
        if future:
            nxt = min(future)
        else:
            nxt = min(candidates) + timedelta(days=1)
        return (nxt - now_utc).total_seconds()

    def _local_hour_label(utc_hour: int) -> str:
        local_h = (utc_hour + tz_offset) % 24
        return LABEL.get(local_h, f"{local_h:02d}:00")

    def _build_report(fired_utc_hour: int) -> str:
        now_utc = datetime.now(timezone.utc)
        midnight_ms = int(now_utc.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)

        mgr = get_runtime_manager()
        running_ids = mgr.running_ids()
        bots = [b for b in list_bots() if b.state != BotState.ARCHIVED]
        expected_running = [b for b in bots if b.state == BotState.RUNNING]

        rows: list[tuple[float, str]] = []  # (pnl, formatted_line)
        total_pnl = 0.0
        total_trades = 0
        active_traders = 0

        for bot in sorted(bots, key=lambda b: b.name):
            summ = contracts_svc.summary(bot.id, since_ms=midnight_ms)
            pnl = summ["realized_pnl"]
            trades = summ["total_count"]
            won = summ["won_count"]
            lost = summ["lost_count"]
            settled = won + lost
            win_rate = f"{won/settled*100:.0f}%" if settled else "—"
            status = "🟢" if bot.id in running_ids else "🔴"

            pnl_str = f"+${pnl:.2f}" if pnl > 0 else (f"-${abs(pnl):.2f}" if pnl < 0 else "$0.00")
            line = f"{status} *{bot.name.replace('Tournament: ', '')}* | {trades}t | {win_rate} | {pnl_str}"
            rows.append((pnl, line))
            total_pnl += pnl
            total_trades += trades
            if trades > 0:
                active_traders += 1

        # Sort by PnL descending
        rows.sort(key=lambda x: x[0], reverse=True)

        running_count = len([b for b in expected_running if b.id in running_ids])
        expected_count = len(expected_running)
        health = "🟢" if running_count == expected_count else "🔴"
        label = _local_hour_label(fired_utc_hour)
        date_str = now_utc.strftime("%a %d %b %Y")
        total_str = f"+${total_pnl:.2f}" if total_pnl >= 0 else f"-${abs(total_pnl):.2f}"

        lines = [
            f"📊 *Brindle — {label} Report*",
            f"_{date_str}, {now_utc.strftime('%H:%M')} UTC_",
            "",
            f"{health} *Bots: {running_count}/{expected_count} running*",
            "",
            "*Today's performance (since 00:00 UTC)*",
            "Bot | Trades | Win% | PnL",
            "——————————————————",
        ]
        for _, line in rows:
            lines.append(line)
        lines += [
            "——————————————————",
            f"💰 *Portfolio today: {total_str}*  \\|  {total_trades} trades across {active_traders} active bots",
        ]
        return "\n".join(lines)

    # Initial wait
    wait = _seconds_until_next_fire()
    log.info("performance_reporter: first report in %.0f minutes", wait / 60)
    await asyncio.sleep(wait)

    while True:
        try:
            fired_utc_hour = datetime.now(timezone.utc).hour
            report = _build_report(fired_utc_hour)
            telegram.send_raw(report)
            log.info("performance_reporter: report sent")
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("performance_reporter: error building/sending report")

        await asyncio.sleep(_seconds_until_next_fire())


async def _resume_running_bots() -> None:
    """Re-attach runtime loops for bots that were running before a restart.

    The runtime manager is in-memory only. Any bot persisted as RUNNING needs
    its loop re-spawned on startup, otherwise it shows as live in the UI but
    never processes ticks.
    """
    import logging
    log = logging.getLogger("startup")
    from app.bots.models import BotState
    from app.bots.service import list_bots
    mgr = get_runtime_manager()
    for bot in list_bots():
        if bot.state == BotState.RUNNING:
            try:
                await mgr.start(bot)
                log.info("auto-resumed bot=%s name=%s", bot.id, bot.name)
                # Small stagger to avoid hitting broker rate limits on startup
                await asyncio.sleep(2.0)
            except Exception as exc:  # noqa: BLE001
                log.error("failed to auto-resume bot=%s: %s", bot.id, exc)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Brindle Platform",
        version="0.1.0",
        description="Paper-trading-first, broker-agnostic trading bot platform",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _metrics_middleware(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start
        # Normalise dynamic path params so cardinality stays low
        path = request.url.path
        http_requests_total.labels(
            method=request.method, path=path, status=response.status_code
        ).inc()
        http_request_duration_seconds.labels(
            method=request.method, path=path
        ).observe(duration)
        return response

    @app.get("/api/health", tags=["meta"])
    async def health() -> dict:
        return {
            "status": "ok",
            "paper_trading_only": settings.paper_trading_only,
            "live_trading_enabled": settings.live_trading_enabled,
        }

    @app.get("/metrics", tags=["meta"], include_in_schema=False)
    async def metrics() -> Response:
        mgr = get_runtime_manager()
        bots_running.set(len(mgr.running_ids()))
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(auth_router)
    app.include_router(bots_router)
    app.include_router(configs_router)
    app.include_router(audit_router)
    app.include_router(alerts_router)
    app.include_router(research_router)
    app.include_router(chat_router)
    app.include_router(llm_router)
    app.include_router(brokers_router)
    app.include_router(telegram_router)
    return app


app = create_app()
