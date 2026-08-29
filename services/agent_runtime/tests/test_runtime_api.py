from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app, initialize_database


def test_health_is_public() -> None:
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok", "bind": "127.0.0.1"}


def test_runtime_status_requires_token() -> None:
    client = TestClient(app)
    assert client.get("/api/runtime/status").status_code == 401


def test_runtime_status_returns_token_boundary() -> None:
    initialize_database()
    client = TestClient(app)
    response = client.get("/api/runtime/status", headers={"X-Desktop-Token": get_settings().desktop_token})
    assert response.status_code == 200
    payload = response.json()
    assert payload["host"] == "127.0.0.1"
    assert payload["tokenExposedToRenderer"] is False
    assert payload["databaseReady"] is True
