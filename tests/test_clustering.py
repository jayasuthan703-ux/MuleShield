"""Tests for indicator extraction, clustering thresholds and report privacy.

These tests are pure/unit-level: build_clusters() operates on in-memory
report dicts, so the clustering rules can be verified without touching the
development database. The privacy test points the DB at a temp file.
"""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import clustering, db  # noqa: E402

# A realistic report paste: phone (with +91 prefix and an internal space),
# UPI id, phishing URL and two messaging handles. All invented.
REPORT_TEXT = (
    "They asked me to rent my bank account. Call +91 98765 43210 or mail "
    "easyjob@upifake, open https://bonus-offer.test/claim, or DM "
    "@student_earns_fast on Telegram."
)


def test_indicator_extraction_masks_and_hashes() -> None:
    indicators = clustering.extract_indicators(REPORT_TEXT)
    kinds = [i["type"] for i in indicators]

    assert kinds == ["phone", "upi", "url", "telegram"]

    by_kind = {i["type"]: i["value"] for i in indicators}
    # Normalisation: separators and prefix stripped, so the same phone in a
    # different format yields the same value and therefore the same hash.
    assert by_kind["phone"] == "9876543210"
    same_phone = clustering.extract_indicators("ring 9876543210 asap")
    assert same_phone[0]["value"] == by_kind["phone"]
    assert clustering.hash_indicator(
        "phone", by_kind["phone"]
    ) == clustering.hash_indicator("phone", same_phone[0]["value"])

    # Masks follow the documented shapes and never reveal the middle digits.
    assert clustering.mask_indicator("phone", by_kind["phone"]) == "98xxxxxx10"
    assert clustering.mask_indicator("upi", by_kind["upi"]) == "ea***@upifake"
    assert clustering.mask_indicator("url", by_kind["url"]).startswith(
        "bonus-offer.test"
    )
    assert clustering.mask_indicator(
        "telegram", by_kind["telegram"]
    ) == "@stxxxst"

    # Hashes are salted digests - they must not contain the raw value.
    for indicator in indicators:
        digest = clustering.hash_indicator(indicator["type"], indicator["value"])
        assert len(digest) == 32
        assert digest != indicator["value"]
        assert indicator["value"] not in digest

    # No duplicates: mentioning the phone twice yields one indicator.
    dupes = clustering.extract_indicators("9876543210 or 9876543210")
    assert len(dupes) == 1


def test_clustering_threshold_three_reports_activate_alert() -> None:
    def report(rid: int, hashes: list[str]) -> dict:
        return {
            "id": rid,
            "indicator_hashes": hashes,
            "masked_indicators": ["98xxxxxx10"] * len(hashes),
            "campus_tag": f"TAG{rid}",
            "created_at": f"2026-10-25T10:00:{rid:02d}Z",
            "text_vector": None,
        }

    # Two reports sharing an indicator: a cluster, but NOT yet an alert.
    two = [report(1, ["h_shared"]), report(2, ["h_shared"])]
    clusters = clustering.build_clusters(two)
    assert len(clusters) == 1
    assert clusters[0]["count"] == 2
    assert clusters[0]["active"] is False

    # A third matching report crosses the threshold -> active campus alert.
    three = two + [report(3, ["h_shared"])]
    clusters = clustering.build_clusters(three)
    assert len(clusters) == 1
    assert clusters[0]["count"] == 3
    assert clusters[0]["active"] is True
    assert clusters[0]["first_seen"] == "2026-10-25T10:00:01Z"
    assert clusters[0]["last_seen"] == "2026-10-25T10:00:03Z"
    assert clusters[0]["report_ids"] == [1, 2, 3]

    # Unrelated reports stay out of the cluster entirely.
    mixed = three + [report(4, ["h_other"]), report(5, [])]
    clusters = clustering.build_clusters(mixed)
    assert len(clusters) == 1  # singletons are not clusters
    assert clusters[0]["count"] == 3


def test_clustering_links_reports_by_text_similarity() -> None:
    """Near-identical texts cluster even without a shared indicator."""
    scam_a = "Free recharge offer: open the link and enter your OTP to get 500 rupees."
    scam_b = "Free recharge offer: open the link, enter your OTP, get 500 rupees!"
    other = "Hostel mess menu changed to South Indian thali from Monday."

    reports = [
        {
            "id": i,
            "indicator_hashes": [],
            "masked_indicators": [],
            "campus_tag": "CSE",
            "created_at": f"2026-10-25T09:00:0{i}Z",
            "text_vector": clustering.vectorize(text),
        }
        for i, text in enumerate([scam_a, scam_b, other], start=1)
    ]

    sim_ab = clustering.cosine_similarity(
        reports[0]["text_vector"], reports[1]["text_vector"]
    )
    sim_ao = clustering.cosine_similarity(
        reports[0]["text_vector"], reports[2]["text_vector"]
    )
    assert sim_ab >= clustering.SIMILARITY_THRESHOLD
    assert sim_ao < clustering.SIMILARITY_THRESHOLD

    clusters = clustering.build_clusters(reports)
    assert len(clusters) == 1
    assert clusters[0]["report_ids"] == [1, 2]
    assert "text similarity" in clusters[0]["linked_by"]


def test_file_report_never_stores_raw_text(monkeypatch, tmp_path) -> None:
    """End-to-end privacy check: the raw message never reaches the DB."""
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "privacy_test.db")
    db.init_db()

    result = clustering.file_report(REPORT_TEXT, "CSE")

    assert result["masked_indicators"] == [
        "98xxxxxx10",
        "ea***@upifake",
        "bonus-offer.test/cl…",
        "@stxxxst",
    ]
    assert result["report_id"] > 0

    # Inspect every stored column: no cell may contain the raw message or
    # any unmasked indicator from it.
    conn = sqlite3.connect(tmp_path / "privacy_test.db")
    try:
        rows = conn.execute("SELECT * FROM reports").fetchall()
        columns = [d[0] for d in conn.execute("SELECT * FROM reports LIMIT 0").description]
    finally:
        conn.close()

    assert "text" not in [c.lower() for c in columns]
    assert db.raw_text_columns() == []

    assert len(rows) == 1
    for cell in rows[0]:
        cell_str = str(cell)
        assert REPORT_TEXT not in cell_str
        assert "9876543210" not in cell_str
        assert "easyjob@upifake" not in cell_str

    # The row does keep the safe, derived fields.
    row = dict(zip(columns, rows[0]))
    masks = json.loads(row["masked_indicators"])
    assert "98xxxxxx10" in masks
    assert row["text_fingerprint"]  # salted digest, not the message
    assert REPORT_TEXT not in row["text_fingerprint"]
    assert json.loads(row["text_vector"])  # derived TF-IDF features present
