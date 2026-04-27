import os

import pytest
from fastapi.testclient import TestClient

import app.runtime.manager as _mgr_module
from app.auth.service import seed_default_users
from app.core.settings import get_settings
from app.db.engine import use_test_database
from app.main import create_app

_TEST_ADMIN_EMAIL = "admin@test.example"
_TEST_ADMIN_PASSWORD = "test-admin-password-1"
_TEST_DEMO_PASSWORD = "test-demo-password-1"


@pytest.fixture(autouse=True)
def reset_store():
    """Isolate each test — in-memory SQLite + seeded users per test."""
    os.environ["SUPER_ADMIN_EMAIL"] = _TEST_ADMIN_EMAIL
    os.environ["SUPER_ADMIN_PASSWORD"] = _TEST_ADMIN_PASSWORD
    os.environ["SEED_DEMO_USERS"] = "true"
    os.environ["SEED_DEMO_PASSWORD"] = _TEST_DEMO_PASSWORD
    get_settings.cache_clear()
    use_test_database()
    seed_default_users()
    yield
    # Reset singleton so the next test gets a fresh RuntimeManager with no
    # stale tasks.  Lifespan shutdown already cancelled running tasks via
    # stop_all() before control reaches here.
    _mgr_module._manager = None


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    # Use as context manager so the anyio portal persists across requests,
    # which keeps asyncio.create_task() tasks alive between HTTP calls.
    with TestClient(app) as c:
        yield c


@pytest.fixture
def admin_token(client: TestClient) -> str:
    r = client.post(
        "/api/auth/login",
        json={"email": _TEST_ADMIN_EMAIL, "password": _TEST_ADMIN_PASSWORD},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def reviewer_token(client: TestClient) -> str:
    r = client.post(
        "/api/auth/login",
        json={"email": "reviewer@example.com", "password": _TEST_DEMO_PASSWORD},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
