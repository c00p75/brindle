from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """Immutable record of an action. Append-only."""

    id: str
    actor_email: str
    actor_role: str
    action: str  # e.g. "bot.create", "config.apply", "bot.start"
    resource_type: str  # e.g. "bot", "config"
    resource_id: str
    at_ms: int
    diff: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    outcome: str = "ok"  # "ok" | "error"
    reason: str | None = None
