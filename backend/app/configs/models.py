from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from app.bots.models import BotConfig


class ConfigStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    APPLIED = "applied"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"


class ConfigVersion(BaseModel):
    """Immutable record of a single config version for a bot.

    Active config is the APPLIED version with the highest version number.
    Applying creates a new record; prior applied version is marked SUPERSEDED.
    """

    bot_id: str
    version: int
    status: ConfigStatus
    config: BotConfig
    created_by: str
    created_at_ms: int
    applied_at_ms: int | None = None
    approved_by: str | None = None
    validation_errors: list[str] = []
    validation_warnings: list[str] = []
    parent_version: int | None = None  # for rollbacks
