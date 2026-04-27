"""Prometheus metrics registry.

All counters/gauges/histograms live here so they can be imported from
anywhere without creating duplicate metric names.
"""
from prometheus_client import Counter, Gauge, Histogram

http_requests_total = Counter(
    "tradingbot_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "tradingbot_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

orders_total = Counter(
    "tradingbot_orders_total",
    "Orders submitted through ExecutionService",
    ["bot_id", "status"],
)

risk_rejections_total = Counter(
    "tradingbot_risk_rejections_total",
    "Orders rejected by the risk engine",
    ["bot_id", "reason"],
)

bots_running = Gauge(
    "tradingbot_bots_running",
    "Number of bots currently running",
)

audit_events_total = Counter(
    "tradingbot_audit_events_total",
    "Audit events recorded",
    ["action"],
)

backtest_runs_total = Counter(
    "tradingbot_backtest_runs_total",
    "Backtest runs completed",
    ["strategy_id", "outcome"],
)
