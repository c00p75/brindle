from app.auth.jwt import hash_password, verify_password
from app.auth.models import User
from app.auth.rbac import Role
from app.core.ids import new_id
from app.db.store import get_store

USERS = "users"


def seed_default_users() -> None:
    """Create default users for development only. Remove before prod."""
    store = get_store()
    if store.list(USERS):
        return
    defaults = [
        ("admin@example.com", "admin12345", Role.ADMIN),
        ("operator@example.com", "operator12345", Role.OPERATOR),
        ("reviewer@example.com", "reviewer12345", Role.REVIEWER),
        ("viewer@example.com", "viewer12345", Role.VIEWER),
    ]
    for email, password, role in defaults:
        u = User(
            id=new_id("usr"),
            email=email,
            role=role,
            password_hash=hash_password(password),
            is_active=True,
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
