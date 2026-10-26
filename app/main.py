"""MuleShield FastAPI entrypoint.

Serves the static single-page frontend at "/" and exposes the JSON API
under "/api". Feature modules are wired in here as they are built.
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import anomaly, clustering, db, detector

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="MuleShield",
    description="Helps students recognise and refuse money-mule recruitment offers.",
    version="0.1.0",
)


class AnalyzeRequest(BaseModel):
    """POST body for /api/analyze. The text is analysed in memory only."""

    text: str | None = ""


class ReportRequest(BaseModel):
    """POST body for /api/report.

    Only the message text (for extraction at submission time) and a campus
    tag are accepted - never names, phone numbers of the reporter or any
    other personal detail.
    """

    text: str = Field(default="", max_length=7000)
    campus_tag: str = Field(default="", max_length=50)


@app.get("/api/health")
def health() -> dict:
    """Liveness probe used by tests and the demo script."""
    return {"status": "ok", "app": "MuleShield", "version": "0.1.0"}


@app.post("/api/analyze")
def analyze_message(payload: AnalyzeRequest) -> dict:
    """Score a recruitment message with the hybrid detector.

    Privacy: the submitted text is never stored, logged or transmitted -
    see app/detector.py. Inputs over 5,000 characters are truncated by the
    detector; empty input returns a zero-risk response.
    """
    return detector.analyze(payload.text or "")


@app.post("/api/report")
def submit_report(payload: ReportRequest) -> dict:
    """File one anonymous report and return how it clustered.

    Privacy: indicators are salted-hashed and masked at submission time,
    the text is vectorised and then discarded - nothing free-text is ever
    written to disk (see app/clustering.py and app/db.py).
    """
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="Paste the suspicious message text so indicators can be extracted.",
        )
    return clustering.file_report(text, payload.campus_tag)


@app.get("/api/alerts")
def list_alerts() -> dict:
    """Current clusters; count >= 3 matching reports = active campus alert."""
    return clustering.get_alerts()


@app.get("/api/anomalies")
def list_anomalies() -> dict:
    """Ranked synthetic-account anomaly scores for the bank dashboard.

    Model: Isolation Forest over per-account features, blended with
    transparent rule points. See app/anomaly.py. All data is synthetic.
    """
    return anomaly.get_anomalies()


@app.get("/api/anomalies/{account_id}")
def anomaly_detail(account_id: str) -> dict:
    """Score breakdown plus daily money-flow series for one account."""
    detail = anomaly.get_account_detail(account_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Unknown account id.")
    return detail


# Static frontend is mounted last so API routes take precedence.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

# Ensure the schema exists and demo data is present whenever the app module
# is imported (server start, tests, dev tools). Idempotent.
db.init_db()
clustering.ensure_seeded()
