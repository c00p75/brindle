from app.auth.jwt import hash_password, verify_password
from app.auth.models import User
from app.auth.rbac import Role
from app.core.settings import get_settings
from app.core.ids import new_id
from app.db.store import get_store

USERS = "users"


def seed_default_users() -> None:
    """Seed a bootstrap super-admin and optional demo users."""
    store = get_store()
    settings = get_settings()
    super_admin_email = settings.super_admin_email.strip().lower()
    if not super_admin_email or not settings.super_admin_password:
        raise ValueError("SUPER_ADMIN_EMAIL and SUPER_ADMIN_PASSWORD must be set")

    existing = find_by_email(super_admin_email)
    if existing:
        existing.role = Role.ADMIN
        existing.password_hash = hash_password(settings.super_admin_password)
        existing.is_active = True
        existing.is_super_admin = True
        store.put(USERS, existing.email, existing.model_dump())
    else:
        super_admin = User(
            id=new_id("usr"),
            email=super_admin_email,
            role=Role.ADMIN,
            password_hash=hash_password(settings.super_admin_password),
            is_active=True,
            is_super_admin=True,
        )
        store.put(USERS, super_admin.email, super_admin.model_dump())

    if not settings.seed_demo_users:
        return

    defaults = [
        ("operator@example.com", "operator12345", Role.OPERATOR),
        ("reviewer@example.com", "reviewer12345", Role.REVIEWER),
        ("viewer@example.com", "viewer12345", Role.VIEWER),
    ]
    for email, password, role in defaults:
        if find_by_email(email):
            continue
        u = User(
            id=new_id("usr"),
            email=email,
            role=role,
            password_hash=hash_password(password),
            is_active=True,
            is_super_admin=False,
        )
        store.put(USERS, u.email, u.model_dump())


def find_by_email(email: str) -> User | None:
    raw = get_store().get(USERS, email)
    return User(**raw) if raw else None


def authenticate(email: str, password: str) -> User | None:
    user = find_by_email(email)
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
