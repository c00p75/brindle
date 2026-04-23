from fastapi import APIRouter, Depends, HTTPException

from app.alerts.models import Alert, AlertStatus
from app.alerts.service import acknowledge, list_alerts
from app.auth.deps import require
from app.auth.models import User

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
async def list_all(status: AlertStatus | None = None, _: User = Depends(require("bot:read"))) -> list[Alert]:
    return list_alerts(status)


@router.post("/{alert_id}/ack")
async def ack(alert_id: str, user: User = Depends(require("alert:ack"))) -> Alert:
    alert = acknowledge(alert_id, actor_email=user.email)
    if alert is None:
        raise HTTPException(404, "alert not found")
    return alert
