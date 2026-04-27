import logging
import secrets
from sqlalchemy import select

from app.auth.jwt import hash_password, verify_password
from app.auth.models import User
from app.auth.rbac import Role
from app.core.ids import new_id
from app.core.settings import get_settings
from app.core.time import now_epoch_ms
from app.db.engine import session_scope
from app.db.orm import UserRow

log = logging.getLogger("auth")

# In-memory password reset tokens: {token: (email, expires_at_ms)}
_reset_tokens: dict[str, tuple[str, int]] = {}
_RESET_TOKEN_TTL_MS = 15 * 60 * 1000  # 15 minutes


def _row_to_user(row: UserRow) -> User:
    return User(
        id=row.id,
        email=row.email,
        role=Role(row.role),
        password_hash=row.password_hash,
        is_active=row.is_active,
        is_super_admin=row.is_super_admin,
        totp_secret=row.totp_secret,
        totp_enabled=row.totp_enabled,
    )


def find_by_email(email: str) -> User | None:
    normalized = email.strip().lower()
    with session_scope() as s:
        row = s.execute(
            select(UserRow).where(UserRow.email == normalized)
        ).scalar_one_or_none()
        return _row_to_user(row) if row else None


def authenticate(email: str, password: str) -> User | None:
    user = find_by_email(email)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


# ---------------------------------------------------------------------------
# TOTP
# ---------------------------------------------------------------------------

def totp_setup(email: str) -> tuple[str, str]:
    """Generate a new TOTP secret for the user; return (secret, provisioning_uri).
    The secret is NOT saved yet — call totp_enable() after the user verifies a code.
    """
    import pyotp
    secret = pyotp.random_base32()
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=email, issuer_name="TradingBotPlatform"
    )
    with session_scope() as s:
        row = s.execute(select(UserRow).where(UserRow.email == email.lower())).scalar_one_or_none()
        if row is None:
            raise ValueError("user not found")
        row.totp_secret = secret
    return secret, uri


def totp_verify_and_enable(email: str, code: str) -> bool:
    """Verify a TOTP code against the pending secret and enable MFA."""
    import pyotp
    with session_scope() as s:
        row = s.execute(select(UserRow).where(UserRow.email == email.lower())).scalar_one_or_none()
        if row is None or not row.totp_secret:
            return False
        totp = pyotp.TOTP(row.totp_secret)
        if not totp.verify(code, valid_window=1):
            return False
        row.totp_enabled = True
    return True


def totp_check(user: User, code: str) -> bool:
    import pyotp
    if not user.totp_secret:
        return False
    return pyotp.TOTP(user.totp_secret).verify(code, valid_window=1)


def totp_disable(email: str) -> None:
    with session_scope() as s:
        row = s.execute(select(UserRow).where(UserRow.email == email.lower())).scalar_one_or_none()
        if row:
            row.totp_secret = None
            row.totp_enabled = False


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------

def request_password_reset(email: str) -> None:
    """Generate a reset token and log it to console (no email infra yet)."""
    user = find_by_email(email)
    if user is None:
        return  # silent — don't reveal whether email exists
    token = secrets.token_urlsafe(32)
    _reset_tokens[token] = (email.lower(), now_epoch_ms() + _RESET_TOKEN_TTL_MS)
    # In production, send via email. For now, log to console.
    log.warning("PASSWORD RESET TOKEN for %s: %s (expires in 15 min)", email, token)


def reset_password(token: str, new_password: str) -> bool:
    entry = _reset_tokens.pop(token, None)
    if entry is None:
        return False
    email, expires_at = entry
    if now_epoch_ms() > expires_at:
        return False
    with session_scope() as s:
        row = s.execute(select(UserRow).where(UserRow.email == email)).scalar_one_or_none()
        if row is None:
            return False
        row.password_hash = hash_password(new_password)
    return True


def seed_default_users() -> None:
    """Seed a bootstrap super-admin and optional demo users.

    Idempotent: re-applies super-admin password and role on every call so
    credential rotation via env takes effect on restart.
    """
    settings = get_settings()
    super_admin_email = settings.super_admin_email.strip().lower()
    if not super_admin_email or not settings.super_admin_password:
        raise ValueError("SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD must be set")

    with session_scope() as s:
        row = s.execute(
            select(UserRow).where(UserRow.email == super_admin_email)
        ).scalar_one_or_none()
        if row:
            row.role = Role.ADMIN.value
            row.password_hash = hash_password(settings.super_admin_password)
            row.is_active = True
            row.is_super_admin = True
        else:
            s.add(
                UserRow(
                    id=new_id("usr"),
                    email=super_admin_email,
                    role=Role.ADMIN.value,
                    password_hash=hash_password(settings.super_admin_password),
                    is_active=True,
                    is_super_admin=True,
                )
            )

        if not settings.seed_demo_users:
            return

        defaults = [
            ("operator@example.com", Role.OPERATOR),
            ("reviewer@example.com", Role.REVIEWER),
            ("viewer@example.com", Role.VIEWER),
        ]
        for email, role in defaults:
            email_lc = email.lower()
            existing = s.execute(
                select(UserRow).where(UserRow.email == email_lc)
            ).scalar_one_or_none()
            if existing:
                continue
            s.add(
                UserRow(
                    id=new_id("usr"),
                    email=email_lc,
                    role=role.value,
                    password_hash=hash_password(settings.seed_demo_password),
                    is_active=True,
                    is_super_admin=False,
                )
            )
