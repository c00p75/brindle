from fastapi import APIRouter, Depends

from app.audit.models import AuditEvent
from app.audit.service import list_events
from app.auth.deps import require
from app.auth.models import User

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
async def list_audit(resource_id: str | None = None, _: User = Depends(require("audit:read"))) -> list[AuditEvent]:
    return list_events(resource_id)
