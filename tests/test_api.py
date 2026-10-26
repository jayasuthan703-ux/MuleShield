"""API-level tests for POST /api/analyze, POST /api/report, GET /api/alerts."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_analyze_endpoint_returns_detector_output() -> None:
    res = client.post(
        "/api/analyze",
        json={
            "text": "Forward the money you receive, 10 percent commission, "
                    "no experience needed, keep it secret for just a few days."
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["level"] == "High"
    assert 65 <= body["risk_score"] <= 100
    assert body["matched_signals"]
    assert "not legal advice" in body["legal_risk_summary"]
    assert body["recommended_actions"]
    assert "Nothing is stored" in body["privacy_note"] or "never stored" in body["privacy_note"]


def test_analyze_endpoint_handles_empty_and_long_input() -> None:
    empty = client.post("/api/analyze", json={"text": ""})
    assert empty.status_code == 200
    assert empty.json()["note"] == "empty_input"

    long = client.post("/api/analyze", json={"text": "please forward the money " * 400})
    assert long.status_code == 200
    assert long.json()["note"] == "truncated_to_5000_chars"


def test_report_endpoint_rejects_empty_text(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "api_report.db")
    db.init_db()

    res = client.post("/api/report", json={"text": "", "campus_tag": "CSE"})
    assert res.status_code == 400
    assert "Paste" in res.json()["detail"]

    whitespace = client.post("/api/report", json={"text": "   \n  "})
    assert whitespace.status_code == 400


def test_report_endpoint_accepts_long_text_without_echoing_it(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "api_report.db")
    db.init_db()

    long_text = ("Call 9876543210 for part-time work. " * 250)[:7000]
    assert len(long_text) == 7000  # matches the textarea maxlength

    res = client.post(
        "/api/report", json={"text": long_text, "campus_tag": "ECE"}
    )
    assert res.status_code == 200
    body = res.json()

    # Repeated indicators deduplicate to one mask.
    assert body["masked_indicators"] == ["98xxxxxx10"]
    # The raw text must never come back (or be stored).
    assert long_text[:60] not in json.dumps(body)


def test_alerts_endpoint_shape() -> None:
    res = client.get("/api/alerts")
    assert res.status_code == 200
    body = res.json()
    for key in (
        "clusters",
        "active_alerts",
        "watching",
        "total_reports",
        "min_for_alert",
    ):
        assert key in body
    assert body["min_for_alert"] == 3
    for cluster in body["clusters"]:
        assert {
            "cluster_id",
            "count",
            "first_seen",
            "last_seen",
            "masked_indicators",
        } <= set(cluster)
        assert cluster["count"] >= 2
