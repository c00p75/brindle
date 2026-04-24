from sqlalchemy import select

from app.auth.jwt import hash_password, verify_password
from app.auth.models import User
from app.auth.rbac import Role
from app.core.ids import new_id
from app.core.settings import get_settings
from app.db.engine import session_scope
from app.db.orm import UserRow


def _row_to_user(row: UserRow) -> User:
    return User(
        id=row.id,
        email=row.email,
        role=Role(row.role),
        password_hash=row.password_hash,
        is_active=row.is_active,
        is_super_admin=row.is_super_admin,
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
            ("operator@example.com", "operator12345", Role.OPERATOR),
            ("reviewer@example.com", "reviewer12345", Role.REVIEWER),
            ("viewer@example.com", "viewer12345", Role.VIEWER),
        ]
        for email, password, role in defaults:
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
                    password_hash=hash_password(password),
                    is_active=True,
                    is_super_admin=False,
                )
            )
