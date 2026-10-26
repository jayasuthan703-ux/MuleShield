"""SQLite storage for anonymous MuleShield reports.

Privacy invariants enforced here:

* The raw message is NEVER written to disk. Callers pass only derived data:
  salted indicator hashes, masked indicator displays, a salted text
  fingerprint, and an optional TF-IDF vector (derived features, not text).
* Indicator hashing uses a per-install random salt, generated on first run and
  stored in ``data/.indicator_salt``. Treat that file like a secret: it lets
  the server recognise that two reports mention the same indicator without
  ever knowing what the indicator was. Delete it to re-key.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "muleshield.db"
SALT_PATH = DATA_DIR / ".indicator_salt"

#: Column order kept explicit so tests and the API agree on the shape.
REPORT_COLUMNS = (
    "id",
    "indicator_hashes",
    "masked_indicators",
    "campus_tag",
    "created_at",
    "text_fingerprint",
    "text_vector",
)


def _load_salt() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if SALT_PATH.exists():
        existing = SALT_PATH.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    salt = secrets.token_hex(32)
    SALT_PATH.write_text(salt, encoding="utf-8")
    return salt


#: Loaded once at import (created on first run).
SALT = _load_salt()


def hash_value(kind: str, value: str) -> str:
    """Salted SHA-256 digest (truncated to 128 bits) of a normalised value."""
    material = f"{SALT}|{kind}|{value}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()[:32]


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the reports table if it does not exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                indicator_hashes TEXT NOT NULL DEFAULT '[]',
                masked_indicators TEXT NOT NULL DEFAULT '[]',
                campus_tag TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                text_fingerprint TEXT,
                text_vector TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_created ON reports(created_at)"
        )
        conn.commit()
    finally:
        conn.close()


def insert_report(
    indicator_hashes: list[str],
    masked_indicators: list[str],
    campus_tag: str,
    created_at: Optional[str] = None,
    text_fingerprint: Optional[str] = None,
    text_vector: Optional[list] = None,
) -> int:
    """Insert one anonymous report and return its id.

    ``indicator_hashes`` and ``masked_indicators`` are parallel arrays
    (same order). ``text_vector`` is a list of ``[term_index, weight]``
    pairs - derived features, not recoverable text.
    """
    conn = _connect()
    try:
        cur = conn.execute(
            """
            INSERT INTO reports
                (indicator_hashes, masked_indicators, campus_tag, created_at,
                 text_fingerprint, text_vector)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                json.dumps(indicator_hashes, ensure_ascii=False),
                json.dumps(masked_indicators, ensure_ascii=False),
                campus_tag,
                created_at or utcnow_iso(),
                text_fingerprint,
                json.dumps(text_vector) if text_vector else None,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def list_reports() -> list[dict[str, Any]]:
    """All reports, newest fields parsed. Never contains raw text."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, indicator_hashes, masked_indicators, campus_tag, "
            "created_at, text_fingerprint, text_vector FROM reports ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    reports: list[dict[str, Any]] = []
    for row in rows:
        reports.append(
            {
                "id": row["id"],
                "indicator_hashes": json.loads(row["indicator_hashes"] or "[]"),
                "masked_indicators": json.loads(row["masked_indicators"] or "[]"),
                "campus_tag": row["campus_tag"] or "",
                "created_at": row["created_at"],
                "text_fingerprint": row["text_fingerprint"],
                "text_vector": json.loads(row["text_vector"])
                if row["text_vector"]
                else None,
            }
        )
    return reports


def get_report(report_id: int) -> Optional[dict[str, Any]]:
    for report in list_reports():
        if report["id"] == report_id:
            return report
    return None


def count_reports() -> int:
    conn = _connect()
    try:
        return int(conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0])
    finally:
        conn.close()


def clear_reports() -> None:
    """Wipe all reports (used by dev tooling/tests)."""
    conn = _connect()
    try:
        conn.execute("DELETE FROM reports")
        conn.commit()
    finally:
        conn.close()


def raw_text_columns() -> list[str]:
    """Safety helper: names of columns that would hold raw text (none)."""
    conn = _connect()
    try:
        rows = conn.execute("PRAGMA table_info(reports)").fetchall()
    finally:
        conn.close()
    forbidden = {"text", "message", "raw_text", "body"}
    return [r["name"] for r in rows if r["name"].lower() in forbidden]
