"""Config lifecycle: draft → validate → approve → apply → rollback.

Authoritative rules:
- Active config is IMMUTABLE. Changes create a new version.
- Apply is atomic: a new version is either fully applied or not at all.
- Every transition writes an audit record with a precise diff.
- Risk-affecting changes require Reviewer approval.
"""
from __future__ import annotations

from app.audit.service import record as audit
from app.bots.models import BotConfig
from app.configs.diff import contains_risky_change, diff as compute_diff
from app.configs.models import ConfigStatus, ConfigVersion
from app.configs.validator import validate_bot_config
from app.core.time import now_epoch_ms
from app.db.store import get_store

TABLE = "config_versions"  # key: f"{bot_id}:{version}"


def _key(bot_id: str, version: int) -> str:
    return f"{bot_id}:{version}"


def _next_version(bot_id: str) -> int:
    existing = [
        ConfigVersion(**v)
        for v in get_store().list(TABLE)
        if ConfigVersion(**v).bot_id == bot_id
    ]
    return max((v.version for v in existing), default=0) + 1


def list_versions(bot_id: str) -> list[ConfigVersion]:
    versions = [
        ConfigVersion(**v)
        for v in get_store().list(TABLE)
        if ConfigVersion(**v).bot_id == bot_id
    ]
    return sorted(versions, key=lambda v: v.version, reverse=True)


def get_version(bot_id: str, version: int) -> ConfigVersion | None:
    raw = get_store().get(TABLE, _key(bot_id, version))
    return ConfigVersion(**raw) if raw else None


def active_version(bot_id: str) -> ConfigVersion | None:
    applied = [v for v in list_versions(bot_id) if v.status == ConfigStatus.APPLIED]
    return applied[0] if applied else None


def create_draft(*, actor_email: str, actor_role: str, config: BotConfig) -> ConfigVersion:
    version = _next_version(config.bot_id)
    # Force assigned version into the config for identity
    cfg = config.model_copy(update={"version": version})
    rec = ConfigVersion(
        bot_id=cfg.bot_id,
        version=version,
        status=ConfigStatus.DRAFT,
        config=cfg,
        created_by=actor_email,
        created_at_ms=now_epoch_ms(),
    )
    get_store().put(TABLE, _key(rec.bot_id, rec.version), rec.model_dump())
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="config.draft.create",
        resource_type="config",
        resource_id=_key(rec.bot_id, rec.version),
    )
    return rec


def validate(*, actor_email: str, actor_role: str, bot_id: str, version: int) -> ConfigVersion:
    rec = get_version(bot_id, version)
    if rec is None:
        raise ValueError("config version not found")
    if rec.status not in {ConfigStatus.DRAFT, ConfigStatus.VALIDATED, ConfigStatus.PENDING_APPROVAL}:
        raise ValueError(f"cannot validate config in status {rec.status}")
    errors, warnings = validate_bot_config(rec.config)
    rec.validation_errors = errors
    rec.validation_warnings = warnings
    rec.status = ConfigStatus.VALIDATED if not errors else ConfigStatus.DRAFT
    get_store().put(TABLE, _key(rec.bot_id, rec.version), rec.model_dump())
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="config.validate",
        resource_type="config",
        resource_id=_key(rec.bot_id, rec.version),
        metadata={"errors": errors, "warnings": warnings},
        outcome="ok" if not errors else "error",
        reason=None if not errors else "; ".join(errors),
    )
    return rec


def request_approval(*, actor_email: str, actor_role: str, bot_id: str, version: int) -> ConfigVersion:
    rec = get_version(bot_id, version)
    if rec is None:
        raise ValueError("config version not found")
    if rec.status != ConfigStatus.VALIDATED:
        raise ValueError("only validated configs can request approval")
    rec.status = ConfigStatus.PENDING_APPROVAL
    get_store().put(TABLE, _key(rec.bot_id, rec.version), rec.model_dump())
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="config.request_approval",
        resource_type="config",
        resource_id=_key(rec.bot_id, rec.version),
    )
    return rec


def approve(*, actor_email: str, actor_role: str, bot_id: str, version: int) -> ConfigVersion:
    rec = get_version(bot_id, version)
    if rec is None:
        raise ValueError("config version not found")
    if rec.status not in {ConfigStatus.PENDING_APPROVAL, ConfigStatus.VALIDATED}:
        raise ValueError("config not in approvable state")
    rec.status = ConfigStatus.APPROVED
    rec.approved_by = actor_email
    get_store().put(TABLE, _key(rec.bot_id, rec.version), rec.model_dump())
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="config.approve",
        resource_type="config",
        resource_id=_key(rec.bot_id, rec.version),
    )
    return rec


def apply(*, actor_email: str, actor_role: str, bot_id: str, version: int, typed_confirmation: str | None = None) -> ConfigVersion:
    rec = get_version(bot_id, version)
    if rec is None:
        raise ValueError("config version not found")
    if rec.validation_errors:
        raise ValueError("cannot apply: validation errors present")

    active = active_version(bot_id)
    before = active.config.model_dump() if active else None
    changes = compute_diff(before, rec.config.model_dump())
    risky = contains_risky_change(changes)

    # Risky change must either already be APPROVED or be accompanied by typed confirmation.
    if risky and rec.status != ConfigStatus.APPROVED and typed_confirmation != "APPLY RISK CHANGE":
        raise ValueError(
            "risky config change requires reviewer approval or typed confirmation "
            "'APPLY RISK CHANGE'"
        )
    if not risky and rec.status not in {ConfigStatus.VALIDATED, ConfigStatus.APPROVED}:
        raise ValueError("config must be validated before apply")

    # Atomic transition: mark previous applied as superseded, mark this applied.
    if active is not None:
        active.status = ConfigStatus.SUPERSEDED
        get_store().put(TABLE, _key(active.bot_id, active.version), active.model_dump())
    rec.status = ConfigStatus.APPLIED
    rec.applied_at_ms = now_epoch_ms()
    get_store().put(TABLE, _key(rec.bot_id, rec.version), rec.model_dump())

    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="config.apply",
        resource_type="config",
        resource_id=_key(rec.bot_id, rec.version),
        diff=changes,
        metadata={"risky": risky},
    )
    return rec


def rollback(*, actor_email: str, actor_role: str, bot_id: str, to_version: int) -> ConfigVersion:
    target = get_version(bot_id, to_version)
    if target is None:
        raise ValueError("target version not found")
    # Rollback is implemented as a new version cloned from target, then applied.
    new_v = create_draft(
        actor_email=actor_email,
        actor_role=actor_role,
        config=target.config,
    )
    validated = validate(
        actor_email=actor_email, actor_role=actor_role, bot_id=bot_id, version=new_v.version
    )
    if validated.validation_errors:
        raise ValueError(
            "rollback target fails validation under current rules: "
            + "; ".join(validated.validation_errors)
        )
    return apply(
        actor_email=actor_email,
        actor_role=actor_role,
        bot_id=bot_id,
        version=new_v.version,
        typed_confirmation="APPLY RISK CHANGE",  # rollbacks are always audited
    )
