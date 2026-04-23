from __future__ import annotations

from app.alerts.models import Alert, AlertStatus, Severity
from app.core.ids import new_id
from app.core.time import now_epoch_ms
from app.db.store import get_store

TABLE = "alerts"


def emit(*, severity: Severity, source: str, message: str, bot_id: str | None = None, metadata: dict | None = None) -> Alert:
    alert = Alert(
        id=new_id("alt"),
        severity=severity,
        source=source,
        message=message,
        bot_id=bot_id,
        created_at_ms=now_epoch_ms(),
        metadata=metadata or {},
    )
    get_store().put(TABLE, alert.id, alert.model_dump())
    return alert


def list_alerts(status: AlertStatus | None = None) -> list[Alert]:
    raws = get_store().list(TABLE)
    alerts = [Alert(**r) for r in raws]
    if status:
        alerts = [a for a in alerts if a.status == status]
    return sorted(alerts, key=lambda a: a.created_at_ms, reverse=True)


def acknowledge(alert_id: str, actor_email: str) -> Alert | None:
    raw = get_store().get(TABLE, alert_id)
    if not raw:
        return None
    alert = Alert(**raw)
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.acknowledged_by = actor_email
    alert.acknowledged_at_ms = now_epoch_ms()
    get_store().put(TABLE, alert.id, alert.model_dump())
    return alert
