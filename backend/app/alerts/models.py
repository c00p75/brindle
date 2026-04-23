from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class Alert(BaseModel):
    id: str
    severity: Severity
    status: AlertStatus = AlertStatus.ACTIVE
    source: str  # e.g. "risk", "adapter", "data"
    message: str
    bot_id: str | None = None
    created_at_ms: int
    acknowledged_by: str | None = None
    acknowledged_at_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
