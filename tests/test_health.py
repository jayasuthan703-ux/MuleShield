"""Scaffold smoke tests. Feature tests are added as modules are built."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["app"] == "MuleShield"


def test_index_served_at_root() -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "MuleShield" in res.text
