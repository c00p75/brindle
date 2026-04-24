import os

import pytest
from fastapi.testclient import TestClient

from app.auth.service import seed_default_users
from app.core.settings import get_settings
from app.db.engine import use_test_database
from app.main import create_app


@pytest.fixture(autouse=True)
def reset_store():
    """Isolate each test — in-memory SQLite + seeded users per test."""
    os.environ["SUPER_ADMIN_EMAIL"] = "georgecoopmsapenda@gmail.com"
    os.environ["SUPER_ADMIN_PASSWORD"] = "John16:33"
    os.environ["SEED_DEMO_USERS"] = "true"
    get_settings.cache_clear()
    use_test_database()
    seed_default_users()
    yield


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


@pytest.fixture
def admin_token(client: TestClient) -> str:
    r = client.post(
        "/api/auth/login",
        json={"email": "georgecoopmsapenda@gmail.com", "password": "John16:33"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def reviewer_token(client: TestClient) -> str:
    r = client.post(
        "/api/auth/login",
        json={"email": "reviewer@example.com", "password": "reviewer12345"},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
