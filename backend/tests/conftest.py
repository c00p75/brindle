import pytest
from fastapi.testclient import TestClient

from app.auth.service import seed_default_users
from app.db.store import get_store
from app.main import create_app


@pytest.fixture(autouse=True)
def reset_store():
    """Isolate each test — in-memory store state must not leak."""
    store = get_store()
    store._tables.clear()
    store._lists.clear()
    seed_default_users()
    yield


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


@pytest.fixture
def admin_token(client: TestClient) -> str:
    r = client.post("/api/auth/login", json={"email": "admin@example.com", "password": "admin12345"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def reviewer_token(client: TestClient) -> str:
    r = client.post("/api/auth/login", json={"email": "reviewer@example.com", "password": "reviewer12345"})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
