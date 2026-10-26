"""Indicator extraction, report clustering and campus alerts.

Pipeline for one report (POST /api/report):

    raw text ──regex──> indicators ──mask──> "98xxxxxx21"   (safe to show)
                        └──salted hash──> "3f9a…"           (stored)
    raw text ──tfidf──> sparse vector                       (stored)
    raw text ──────────> DISCARDED, never stored or logged

Clusters are formed when two reports share an indicator hash (same salted
digest) or have high TF-IDF cosine similarity (>= SIMILARITY_THRESHOLD).
A cluster with >= MIN_FOR_ACTIVE_ALERT reports becomes an active campus
alert.

Everything here is synthetic/demo oriented: no network calls, no personal
data, no raw message text ever reaches storage.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from . import db

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

#: Cosine similarity at or above which two reports are treated as the same
#: campaign (TF-IDF vectors are L2-normalised, so this is plain cosine).
SIMILARITY_THRESHOLD = 0.45

#: Reports needed before a cluster is flagged as an active campus alert.
MIN_FOR_ACTIVE_ALERT = 3

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "messages.csv"

# ---------------------------------------------------------------------------
# Indicator extraction (regex only - offline, no external services)
# ---------------------------------------------------------------------------

#: Indian mobile numbers, with or without +91/0 prefix and with optional
#: separators inside the number (e.g. "98765 43210").
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?91[\s-]?)?(?:0[\s-]?)?([6-9](?:[\s-]?\d){9})(?!\d)"
)

#: UPI-style identifiers (also catches plain e-mails, which are reportable too).
UPI_RE = re.compile(r"\b[a-z0-9][a-z0-9._-]{1,64}@[a-z]{2,32}\b", re.IGNORECASE)

#: Web links.
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

#: Messaging links and handles.
TELEGRAM_LINK_RE = re.compile(r"(?:t\.me|telegram\.me)/([A-Za-z0-9_]{5,32})", re.I)
WHATSAPP_INVITE_RE = re.compile(r"chat\.whatsapp\.com/([A-Za-z0-9]{10,})", re.I)
WHATSAPP_ME_RE = re.compile(r"wa\.me/(\d{10,15})", re.I)
TELEGRAM_HANDLE_RE = re.compile(r"(?<![\w@])@([A-Za-z][A-Za-z0-9_]{4,32})\b")

INDICATOR_ORDER = ("phone", "upi", "url", "telegram", "whatsapp")


def _clean_url(url: str) -> str:
    return url.rstrip(".,;:!?)\"'")


def extract_indicators(text: str) -> list[dict[str, str]]:
    """Return normalised indicators found in ``text``: [{type, value}].

    Values are normalised (phones reduced to 10 digits, handles lower-cased,
    trailing punctuation stripped) so that two reports mentioning the same
    indicator in slightly different formats still collide.
    """
    if not text:
        return []

    found: dict[tuple[str, str], dict[str, str]] = {}

    def add(kind: str, value: str) -> None:
        value = value.strip()
        if not value:
            return
        found.setdefault((kind, value), {"type": kind, "value": value})

    for match in PHONE_RE.finditer(text):
        add("phone", re.sub(r"\D", "", match.group(1)))

    for match in UPI_RE.finditer(text):
        add("upi", match.group(0).lower())

    for match in URL_RE.finditer(text):
        add("url", _clean_url(match.group(0)))

    for match in TELEGRAM_LINK_RE.finditer(text):
        add("telegram", f"t.me/{match.group(1)}")

    for match in WHATSAPP_INVITE_RE.finditer(text):
        add("whatsapp", f"chat.whatsapp.com/{match.group(1)}")

    for match in WHATSAPP_ME_RE.finditer(text):
        add("whatsapp", f"wa.me/{match.group(1)}")

    for match in TELEGRAM_HANDLE_RE.finditer(text):
        add("telegram", f"@{match.group(1).lower()}")

    # Preserve INDICATOR_ORDER so masks read consistently.
    ordered = [
        item
        for kind in INDICATOR_ORDER
        for key, item in found.items()
        if key[0] == kind
    ]
    return ordered


def mask_indicator(kind: str, value: str) -> str:
    """Display-safe mask, e.g. 9876543210 -> '98xxxxxx21'."""
    if kind == "phone":
        digits = re.sub(r"\D", "", value)
        if len(digits) < 5:
            return "x" * max(len(digits), 2)
        return f"{digits[:2]}{'x' * (len(digits) - 4)}{digits[-2:]}"
    if kind == "upi" and "@" in value:
        user, _, domain = value.partition("@")
        head = user[:2] if len(user) >= 2 else user
        return f"{head}***@{domain}"
    if kind == "url":
        without_scheme = re.sub(r"^https?://", "", value, flags=re.I)
        without_www = re.sub(r"^www\.", "", without_scheme, flags=re.I)
        head, _, rest = without_www.partition("/")
        tail = f"/{rest[:2]}…" if rest else ""
        return f"{head}{tail}"
    if kind == "telegram":
        if value.startswith("@"):
            user = value[1:]
            return f"@{user[:2]}xxx{user[-2:]}" if len(user) > 5 else "@xxx"
        head, _, user = value.partition("/")
        return f"{head}/{user[:2]}xxx{user[-2:]}" if len(user) > 5 else f"{head}/xxx"
    if kind == "whatsapp":
        head, _, user = value.partition("/")
        if user.isdigit():
            return f"{head}/{user[:2]}xxx{user[-2:]}"
        return f"{head}/{user[:2]}xxx{user[-2:]}" if len(user) > 5 else f"{head}/xxx"
    return value[:2] + "xxx"


def hash_indicator(kind: str, value: str) -> str:
    """Salted hash of the normalised indicator (never the raw form alone)."""
    return db.hash_value(kind, value)


def fingerprint_text(text: str) -> Optional[str]:
    """Salted fingerprint of the normalised message (not the message)."""
    normalised = re.sub(r"\s+", " ", (text or "").strip().lower())
    if not normalised:
        return None
    return db.hash_value("text", normalised)


# ---------------------------------------------------------------------------
# TF-IDF vectorisation (fitted at startup on local data, deterministic)
# ---------------------------------------------------------------------------

_VECTOR_MODEL: Any = None
_VECTOR_INFO: dict[str, Any] = {"fitted": False}


def _fit_vectorizer() -> tuple[Any, dict[str, Any]]:
    """Fit a TF-IDF vectorizer on local synthetic data.

    The vocabulary must be deterministic across restarts so that vectors
    stored earlier stay comparable with newly computed ones. data/messages.csv
    is fixed, so fitting on it every startup is safe; a small built-in corpus
    keeps things working if the file is missing.
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    texts: list[str] = []
    if DATA_FILE.exists():
        try:
            with DATA_FILE.open(encoding="utf-8") as fh:
                texts = [r["text"] for r in csv.DictReader(fh) if r.get("text")]
        except Exception:  # pragma: no cover - defensive
            texts = []
    if len(texts) < 10:
        texts = [
            "receive money in your bank account and forward it",
            "share your otp and upi pin with us today",
            "canteen bill split send your share by upi",
            "assignment deadline moved to friday",
        ]
    vec = TfidfVectorizer(
        ngram_range=(1, 2),
        sublinear_tf=True,
        token_pattern=r"(?u)\b\w+\b",
        min_df=1,
    )
    vec.fit(texts)
    return vec, {"fitted": True, "vocab": len(vec.vocabulary_), "corpus": len(texts)}


def _model() -> Any:
    global _VECTOR_MODEL, _VECTOR_INFO
    if _VECTOR_MODEL is None:
        _VECTOR_MODEL, _VECTOR_INFO = _fit_vectorizer()
    return _VECTOR_MODEL


def vector_info() -> dict[str, Any]:
    _model()
    return dict(_VECTOR_INFO)


def vectorize(text: str) -> Optional[list[list[float]]]:
    """TF-IDF vector as sparse [index, weight] pairs, or None if empty.

    Computed at submission time; the caller discards the text afterwards.
    """
    if not text or not text.strip():
        return None
    row = _model().transform([text]).tocoo()
    return [[int(i), float(v)] for i, v in zip(row.col, row.data)]


def _vec_dict(vec_json: Any) -> dict[int, float]:
    if isinstance(vec_json, str):
        vec_json = json.loads(vec_json or "[]")
    return {int(i): float(v) for i, v in (vec_json or [])}


def cosine_similarity(a: Any, b: Any) -> float:
    """Dot product of two L2-normalised TF-IDF vectors = cosine similarity."""
    da, db_ = _vec_dict(a), _vec_dict(b)
    if not da or not db_:
        return 0.0
    if len(da) > len(db_):
        da, db_ = db_, da
    return sum(w * db_.get(i, 0.0) for i, w in da.items())


# ---------------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------------


def build_clusters(
    reports: list[dict[str, Any]],
    similarity_threshold: float = SIMILARITY_THRESHOLD,
    min_count: int = MIN_FOR_ACTIVE_ALERT,
) -> list[dict[str, Any]]:
    """Group reports sharing an indicator hash or high text similarity.

    Pure function over report dicts - no database access - so the rules are
    directly unit-testable. Returns clusters of 2+ reports, active when
    ``count >= min_count``.
    """
    n = len(reports)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    links: list[tuple[int, int, str]] = []
    for i in range(n):
        hashes_i = set(reports[i].get("indicator_hashes") or [])
        for j in range(i + 1, n):
            hashes_j = set(reports[j].get("indicator_hashes") or [])
            if hashes_i and hashes_j and (hashes_i & hashes_j):
                union(i, j)
                links.append((i, j, "shared indicator"))
                continue
            vec_i = reports[i].get("text_vector")
            vec_j = reports[j].get("text_vector")
            if vec_i and vec_j:
                if cosine_similarity(vec_i, vec_j) >= similarity_threshold:
                    union(i, j)
                    links.append((i, j, "text similarity"))

    groups: dict[int, list[int]] = {}
    for idx in range(n):
        groups.setdefault(find(idx), []).append(idx)

    clusters: list[dict[str, Any]] = []
    for root, members in groups.items():
        if len(members) < 2:
            continue  # a singleton is not a cluster
        member_reports = [reports[m] for m in members]
        methods = sorted(
            {
                method
                for a, b, method in links
                if find(a) == root and find(b) == root
            }
        )
        masks: list[str] = []
        tags: list[str] = []
        for report in member_reports:
            for mask in report.get("masked_indicators") or []:
                if mask not in masks:
                    masks.append(mask)
            tag = report.get("campus_tag") or ""
            if tag and tag not in tags:
                tags.append(tag)
        created = [r.get("created_at") or "" for r in member_reports]
        ids = sorted(int(r["id"]) for r in member_reports)
        count = len(member_reports)
        clusters.append(
            {
                "cluster_id": f"c{ids[0]}",
                "report_ids": ids,
                "count": count,
                "first_seen": min(created),
                "last_seen": max(created),
                "masked_indicators": masks,
                "campus_tags": sorted(tags),
                "active": count >= min_count,
                "linked_by": methods,
            }
        )

    clusters.sort(key=lambda c: (not c["active"], -c["count"], c["first_seen"]))
    return clusters


def get_alerts() -> dict[str, Any]:
    """Current clustering of all stored reports (for GET /api/alerts)."""
    reports = db.list_reports()
    clusters = build_clusters(reports)
    clustered = sum(c["count"] for c in clusters)
    return {
        "clusters": clusters,
        "active_alerts": sum(1 for c in clusters if c["active"]),
        "watching": sum(1 for c in clusters if not c["active"]),
        "unmatched_reports": len(reports) - clustered,
        "total_reports": len(reports),
        "min_for_alert": MIN_FOR_ACTIVE_ALERT,
        "similarity_threshold": SIMILARITY_THRESHOLD,
    }


def cluster_containing(report_id: int) -> Optional[dict[str, Any]]:
    for cluster in build_clusters(db.list_reports()):
        if report_id in cluster["report_ids"]:
            return cluster
    return None


# ---------------------------------------------------------------------------
# Filing a report (the privacy-critical path)
# ---------------------------------------------------------------------------


def file_report(
    text: str, campus_tag: str, created_at: Optional[str] = None
) -> dict[str, Any]:
    """Extract -> hash -> vectorise -> store -> DISCARD the text.

    Returns the API response: masked indicators plus how the report clustered.
    """
    text = text or ""
    campus_tag = (campus_tag or "").strip()[:50] or "unspecified"

    indicators = extract_indicators(text)
    hashes: list[str] = []
    masks: list[str] = []
    for ind in indicators:
        h = hash_indicator(ind["type"], ind["value"])
        if h not in hashes:
            hashes.append(h)
            masks.append(mask_indicator(ind["type"], ind["value"]))

    fingerprint = fingerprint_text(text)
    vector = vectorize(text)  # text -> numbers from here on

    report_id = db.insert_report(
        indicator_hashes=hashes,
        masked_indicators=masks,
        campus_tag=campus_tag,
        created_at=created_at,
        text_fingerprint=fingerprint,
        text_vector=vector,
    )

    # From here the raw text is out of scope entirely: clustering works on
    # hashes, masks and vectors only.
    cluster = cluster_containing(report_id)

    if cluster and cluster["active"]:
        message = (
            f"Your report matches {cluster['count'] - 1} other report(s) - "
            "this is now an ACTIVE campus alert."
        )
    elif cluster:
        message = (
            f"Your report matches {cluster['count'] - 1} other report(s). "
            f"{MIN_FOR_ACTIVE_ALERT} matching reports trigger an active alert."
        )
    else:
        message = (
            "Report stored anonymously. No matching reports yet - yours helps "
            "future ones cluster together."
        )

    return {
        "report_id": report_id,
        "masked_indicators": masks,
        "campus_tag": campus_tag,
        "matched_cluster": cluster,
        "message": message,
        "privacy": (
            "Raw message discarded: only salted hashes, masked indicators, a "
            "campus tag, a timestamp and derived features were stored."
        ),
    }


# ---------------------------------------------------------------------------
# Demo seed data (10 invented reports; raw texts live only in memory here)
# ---------------------------------------------------------------------------

#: (hours ago, campus tag, text) - all invented, no real numbers/names.
#: Three share a phone number (active alert), three share a link campaign
#: (two by URL + one by text similarity -> active alert), two share a UPI id
#: (watching, below threshold), two are unmatched singletons.
SEED_REPORTS: list[tuple[int, str, str]] = [
    (
        30,
        "CSE",
        "Got a WhatsApp message from 9876543210 offering part-time work: "
        "money lands in my account, I forward it, keep 10 percent commission.",
    ),
    (
        20,
        "ECE",
        "Received an offer from +91 98765 43210 asking me to rent my bank "
        "account for a few days. Says no experience needed.",
    ),
    (
        5,
        "MECH",
        "A senior passed me the number 9876543210 that pays students to "
        "transfer money within minutes. Is this safe to try?",
    ),
    (
        30,
        "MBA",
        "Free recharge offer: open https://bonus-offer.test/claim and enter "
        "your OTP to get 500 rupees. Looks like a scam to me.",
    ),
    (
        8,
        "CSE",
        "This link came to me too - https://bonus-offer.test/claim - it wants "
        "my OTP. Reporting it here.",
    ),
    (
        6,
        "ECE",
        "Free recharge offer: open the link and enter your OTP to get 500 "
        "rupees. Has anyone else received this?",
    ),
    (
        15,
        "HOSTEL",
        "Message says to send my UPI ID to easyjob@upifake and receive "
        "payment daily for a part-time job.",
    ),
    (
        12,
        "MBA",
        "Asked to pay a 200 registration fee for an internship to "
        "easyjob@upifake. Blocked them.",
    ),
    (
        3,
        "ECE",
        "A bot DM'd me on t.me/claim_reward_bot asking for my bank account "
        "details to release a prize.",
    ),
    (
        2,
        "CSE",
        "Caller from 9123456789 says I won a prize; pay 900 to claim it. "
        "Asking for my card details.",
    ),
]


def ensure_seeded(force: bool = False) -> bool:
    """Seed 10 fake reports if the table is empty. Returns True if seeded."""
    if not force and db.count_reports() > 0:
        return False
    now = datetime.now(timezone.utc)
    for hours_ago, tag, text in SEED_REPORTS:
        created = (now - timedelta(hours=hours_ago)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        file_report(text, tag, created_at=created)
    return True
