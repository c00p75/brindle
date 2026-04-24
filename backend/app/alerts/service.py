from __future__ import annotations

from sqlalchemy import select

from app.alerts.models import Alert, AlertStatus, Severity
from app.core.ids import new_id
from app.core.time import now_epoch_ms
from app.db.engine import session_scope
from app.db.orm import AlertRow


def _row_to_alert(row: AlertRow) -> Alert:
    return Alert(
        id=row.id,
        severity=Severity(row.severity),
        status=AlertStatus(row.status),
        source=row.source,
        message=row.message,
        bot_id=row.bot_id,
        created_at_ms=row.created_at_ms,
        acknowledged_by=row.acknowledged_by,
        acknowledged_at_ms=row.acknowledged_at_ms,
        metadata=row.meta_ or {},
    )


def emit(
    *,
    severity: Severity,
    source: str,
    message: str,
    bot_id: str | None = None,
    metadata: dict | None = None,
) -> Alert:
    row = AlertRow(
        id=new_id("alt"),
        severity=severity.value,
        status=AlertStatus.ACTIVE.value,
        source=source,
        message=message,
        bot_id=bot_id,
        created_at_ms=now_epoch_ms(),
        meta_=metadata or {},
    )
    with session_scope() as s:
        s.add(row)
        s.flush()
        return _row_to_alert(row)


def list_alerts(status: AlertStatus | None = None) -> list[Alert]:
    with session_scope() as s:
        stmt = select(AlertRow).order_by(AlertRow.created_at_ms.desc())
        if status:
            stmt = stmt.where(AlertRow.status == status.value)
        rows = s.execute(stmt).scalars().all()
        return [_row_to_alert(r) for r in rows]


def acknowledge(alert_id: str, actor_email: str) -> Alert | None:
    with session_scope() as s:
        row = s.get(AlertRow, alert_id)
        if row is None:
            return None
        row.status = AlertStatus.ACKNOWLEDGED.value
        row.acknowledged_by = actor_email
        row.acknowledged_at_ms = now_epoch_ms()
        s.flush()
        return _row_to_alert(row)
