from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.audit.models import AuditEvent
from app.core.ids import new_id
from app.core.metrics import audit_events_total
from app.core.time import now_epoch_ms
from app.db.engine import session_scope
from app.db.orm import AuditRow


def _row_to_event(row: AuditRow) -> AuditEvent:
    return AuditEvent(
        id=row.id,
        actor_email=row.actor_email,
        actor_role=row.actor_role,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        at_ms=row.at_ms,
        diff=row.diff or [],
        metadata=row.meta_ or {},
        outcome=row.outcome,
        reason=row.reason,
    )


def record(
    *,
    actor_email: str,
    actor_role: str,
    action: str,
    resource_type: str,
    resource_id: str,
    diff: list[dict[str, Any]] | None = None,
    metadata: dict[str, Any] | None = None,
    outcome: str = "ok",
    reason: str | None = None,
) -> AuditEvent:
    row = AuditRow(
        id=new_id("aud"),
        actor_email=actor_email,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        at_ms=now_epoch_ms(),
        diff=diff or [],
        meta_=metadata or {},
        outcome=outcome,
        reason=reason,
    )
    with session_scope() as s:
        s.add(row)
        s.flush()
        audit_events_total.labels(action=action).inc()
        return _row_to_event(row)


def list_events(resource_id: str | None = None) -> list[AuditEvent]:
    with session_scope() as s:
        stmt = select(AuditRow).order_by(AuditRow.at_ms.desc(), AuditRow.id.desc())
        if resource_id:
            stmt = stmt.where(AuditRow.resource_id == resource_id)
        rows = s.execute(stmt).scalars().all()
        return [_row_to_event(r) for r in rows]
