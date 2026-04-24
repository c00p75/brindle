"""Config lifecycle: draft → validate → approve → apply → rollback.

Authoritative rules:
- Active config is IMMUTABLE. Changes create a new version.
- Apply is atomic: a new version is either fully applied or not at all.
- Every transition writes an audit record with a precise diff.
- Risk-affecting changes require Reviewer approval.
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.audit.service import record as audit
from app.bots.models import BotConfig
from app.configs.diff import contains_risky_change, diff as compute_diff
from app.configs.models import ConfigStatus, ConfigVersion
from app.configs.validator import validate_bot_config
from app.core.time import now_epoch_ms
from app.db.engine import session_scope
from app.db.orm import ConfigVersionRow


def _key(bot_id: str, version: int) -> str:
    return f"{bot_id}:{version}"


def _row_to_version(row: ConfigVersionRow) -> ConfigVersion:
    return ConfigVersion(
        bot_id=row.bot_id,
        version=row.version,
        status=ConfigStatus(row.status),
        config=BotConfig.model_validate(row.config),
        created_by=row.created_by,
        created_at_ms=row.created_at_ms,
        applied_at_ms=row.applied_at_ms,
        approved_by=row.approved_by,
        validation_errors=list(row.validation_errors or []),
        validation_warnings=list(row.validation_warnings or []),
        parent_version=row.parent_version,
    )


def list_versions(bot_id: str) -> list[ConfigVersion]:
    with session_scope() as s:
        rows = (
            s.execute(
                select(ConfigVersionRow)
                .where(ConfigVersionRow.bot_id == bot_id)
                .order_by(ConfigVersionRow.version.desc())
            )
            .scalars()
            .all()
        )
        return [_row_to_version(r) for r in rows]


def get_version(bot_id: str, version: int) -> ConfigVersion | None:
    with session_scope() as s:
        row = s.get(ConfigVersionRow, (bot_id, version))
        return _row_to_version(row) if row else None


def active_version(bot_id: str) -> ConfigVersion | None:
    with session_scope() as s:
        row = s.execute(
            select(ConfigVersionRow)
            .where(
                ConfigVersionRow.bot_id == bot_id,
                ConfigVersionRow.status == ConfigStatus.APPLIED.value,
            )
            .order_by(ConfigVersionRow.version.desc())
            .limit(1)
        ).scalar_one_or_none()
        return _row_to_version(row) if row else None


def _next_version_in_session(s, bot_id: str) -> int:
    existing_max = s.execute(
        select(func.max(ConfigVersionRow.version)).where(
            ConfigVersionRow.bot_id == bot_id
        )
    ).scalar_one()
    return (existing_max or 0) + 1


def create_draft(
    *, actor_email: str, actor_role: str, config: BotConfig
) -> ConfigVersion:
    with session_scope() as s:
        version = _next_version_in_session(s, config.bot_id)
        cfg = config.model_copy(update={"version": version})
        row = ConfigVersionRow(
            bot_id=cfg.bot_id,
            version=version,
            status=ConfigStatus.DRAFT.value,
            config=cfg.model_dump(),
            created_by=actor_email,
            created_at_ms=now_epoch_ms(),
            applied_at_ms=None,
            approved_by=None,
            validation_errors=[],
            validation_warnings=[],
            parent_version=None,
        )
        s.add(row)
        s.flush()
        rec = _row_to_version(row)
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="config.draft.create",
        resource_type="config",
        resource_id=_key(rec.bot_id, rec.version),
    )
    return rec


def validate(
    *, actor_email: str, actor_role: str, bot_id: str, version: int
) -> ConfigVersion:
    with session_scope() as s:
        row = s.get(ConfigVersionRow, (bot_id, version))
        if row is None:
            raise ValueError("config version not found")
        current_status = ConfigStatus(row.status)
        if current_status not in {
            ConfigStatus.DRAFT,
            ConfigStatus.VALIDATED,
            ConfigStatus.PENDING_APPROVAL,
        }:
            raise ValueError(f"cannot validate config in status {current_status.value}")
        cfg = BotConfig.model_validate(row.config)
        errors, warnings = validate_bot_config(cfg)
        row.validation_errors = errors
        row.validation_warnings = warnings
        row.status = (
            ConfigStatus.VALIDATED.value if not errors else ConfigStatus.DRAFT.value
        )
        s.flush()
        rec = _row_to_version(row)

    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="config.validate",
        resource_type="config",
        resource_id=_key(rec.bot_id, rec.version),
        metadata={"errors": rec.validation_errors, "warnings": rec.validation_warnings},
        outcome="ok" if not rec.validation_errors else "error",
        reason=None if not rec.validation_errors else "; ".join(rec.validation_errors),
    )
    return rec


def request_approval(
    *, actor_email: str, actor_role: str, bot_id: str, version: int
) -> ConfigVersion:
    with session_scope() as s:
        row = s.get(ConfigVersionRow, (bot_id, version))
        if row is None:
            raise ValueError("config version not found")
        if ConfigStatus(row.status) != ConfigStatus.VALIDATED:
            raise ValueError("only validated configs can request approval")
        row.status = ConfigStatus.PENDING_APPROVAL.value
        s.flush()
        rec = _row_to_version(row)
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="config.request_approval",
        resource_type="config",
        resource_id=_key(rec.bot_id, rec.version),
    )
    return rec


def approve(
    *, actor_email: str, actor_role: str, bot_id: str, version: int
) -> ConfigVersion:
    with session_scope() as s:
        row = s.get(ConfigVersionRow, (bot_id, version))
        if row is None:
            raise ValueError("config version not found")
        if ConfigStatus(row.status) not in {
            ConfigStatus.PENDING_APPROVAL,
            ConfigStatus.VALIDATED,
        }:
            raise ValueError("config not in approvable state")
        row.status = ConfigStatus.APPROVED.value
        row.approved_by = actor_email
        s.flush()
        rec = _row_to_version(row)
    audit(
        actor_email=actor_email,
        actor_role=actor_role,
        action="config.approve",
        resource_type="config",
        resource_id=_key(rec.bot_id, rec.version),
    )
    return rec


def apply(
    *,
    actor_email: str,
    actor_role: str,
    bot_id: str,
    version: int,
    typed_confirmation: str | None = None,
) -> ConfigVersion:
    with session_scope() as s:
        row = s.get(ConfigVersionRow, (bot_id, version))
        if row is None:
            raise ValueError("config version not found")
        if row.validation_errors:
            raise ValueError("cannot apply: validation errors present")

        # Current active
        active_row = s.execute(
            select(ConfigVersionRow)
            .where(
                ConfigVersionRow.bot_id == bot_id,
                ConfigVersionRow.status == ConfigStatus.APPLIED.value,
            )
            .order_by(ConfigVersionRow.version.desc())
            .limit(1)
        ).scalar_one_or_none()

        before = active_row.config if active_row else None
        changes = compute_diff(before, row.config)
        risky = contains_risky_change(changes)

        current_status = ConfigStatus(row.status)
        if (
            risky
            and current_status != ConfigStatus.APPROVED
            and typed_confirmation != "APPLY RISK CHANGE"
        ):
            raise ValueError(
                "risky config change requires reviewer approval or typed "
                "confirmation 'APPLY RISK CHANGE'"
            )
        if not risky and current_status not in {
            ConfigStatus.VALIDATED,
            ConfigStatus.APPROVED,
        }:
            raise ValueError("config must be validated before apply")

        if active_row is not None:
            active_row.status = ConfigStatus.SUPERSEDED.value
        row.status = ConfigStatus.APPLIED.value
        row.applied_at_ms = now_epoch_ms()
        s.flush()
        rec = _row_to_version(row)

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


def rollback(
    *, actor_email: str, actor_role: str, bot_id: str, to_version: int
) -> ConfigVersion:
    target = get_version(bot_id, to_version)
    if target is None:
        raise ValueError("target version not found")
    new_v = create_draft(
        actor_email=actor_email, actor_role=actor_role, config=target.config
    )
    validated = validate(
        actor_email=actor_email,
        actor_role=actor_role,
        bot_id=bot_id,
        version=new_v.version,
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
        typed_confirmation="APPLY RISK CHANGE",  # rollbacks are always audited as risky
    )
