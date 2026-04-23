from __future__ import annotations

from typing import Any

from app.audit.models import AuditEvent
from app.core.ids import new_id
from app.core.time import now_epoch_ms
from app.db.store import get_store

STREAM = "audit_events"


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
    event = AuditEvent(
        id=new_id("aud"),
        actor_email=actor_email,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        at_ms=now_epoch_ms(),
        diff=diff or [],
        metadata=metadata or {},
        outcome=outcome,
        reason=reason,
    )
    get_store().append(STREAM, event.model_dump())
    return event


def list_events(resource_id: str | None = None) -> list[AuditEvent]:
    raws = get_store().stream(STREAM)
    events = [AuditEvent(**r) for r in raws]
    if resource_id:
        events = [e for e in events if e.resource_id == resource_id]
    return list(reversed(events))
