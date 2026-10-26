"""Bank-side anomaly detection over synthetic student-account transactions.

Pipeline:

    data/transactions.csv  (from data/generate_transactions.py)
        -> per-account features  (credits/day, pass-through ratio, unique
           senders, time-to-forward, retained balance, new device/location)
        -> Isolation Forest anomaly score  +  transparent rule features
        -> final score 0-100, ranked list, per-account money-flow series

Everything runs offline on invented data. The dashboard built on top of this
must always display the banner "Synthetic data for demonstration only." -
see ``SYNTH_BANNER``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd

from data import generate_transactions as _gen

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "transactions.csv"

#: Account counts in the synthetic dataset (re-exported for tests/API).
NORMAL_ACCOUNTS = _gen.NORMAL_ACCOUNTS
MULE_ACCOUNTS = _gen.MULE_ACCOUNTS
WINDOW_DAYS = _gen.WINDOW_DAYS

SYNTH_BANNER = "Synthetic data for demonstration only."

#: A debit within this many minutes of a credit counts as pass-through.
PASS_THROUGH_WINDOW_MIN = 120

#: Score at or above which an account is flagged.
FLAG_THRESHOLD = 70
WATCH_THRESHOLD = 45

MODEL_FEATURES = [
    "credits_per_day",
    "unique_senders",
    "pass_through_ratio",
    "avg_forward_minutes",
    "retained_ratio",
    "new_device_ratio",
    "new_location_ratio",
    "max_daily_credits",
    "median_credit_amount",
    "total_credit_amount",
]

#: Transparent rules: name -> (weight, human explanation template).
#: Templates use ``{placeholder}`` substituted at call time by ``evaluate_rules``.
RULES = {
    "rapid_pass_through": (
        30,
        "About {pct} of incoming money left the account within "
        + str(PASS_THROUGH_WINDOW_MIN)
        + " minutes (avg {avg} min).",
    ),
    "many_unrelated_senders": (
        20,
        "{n} distinct senders credited the account - a spray pattern typical "
        "of mule recruitment.",
    ),
    "near_zero_retention": (
        25,
        "Only {pct} of the money that ever entered the account was still "
        "there at the end of the window.",
    ),
    "unfamiliar_device": (
        15,
        "{pct} of transactions used a device never seen in the account's "
        "early history.",
    ),
    "burst_credits": (
        10,
        "{n} separate credits arrived on the busiest single day.",
    ),
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def ensure_data() -> Path:
    """Generate transactions.csv (once) if it is missing."""
    if DATA_PATH.exists():
        return DATA_PATH
    _gen.main()
    return DATA_PATH


def load_transactions() -> pd.DataFrame:
    ensure_data()
    df = pd.read_csv(DATA_PATH)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["amount"] = df["amount"].astype(float)
    df["date"] = df["timestamp"].dt.date
    return df


# ---------------------------------------------------------------------------
# Feature engineering (per account)
# ---------------------------------------------------------------------------


def _pair_pass_through(account: pd.DataFrame) -> tuple[float, float, float]:
    """Match credits to a substantial soon-after debit.

    Returns (matched_credit_amount, total_credit_amount, avg_forward_minutes).

    A credit counts as "passed through" when a debit of at least half its
    size leaves the account within ``PASS_THROUGH_WINDOW_MIN`` minutes to a
    different counterparty - the pooled-funds pattern of a mule account. A
    small lunch purchase after a salary credit does not qualify, and one
    drain debit can settle several credits that arrived together.
    """
    credits = account[account["direction"] == "credit"].sort_values("timestamp")
    debits = account[account["direction"] == "debit"].sort_values("timestamp")

    total_credit = float(credits["amount"].sum())
    if total_credit <= 0 or debits.empty:
        return 0.0, total_credit, 0.0

    matched_amount = 0.0
    forward_minutes: list[float] = []

    debit_times = list(debits["timestamp"])
    debit_amounts = list(debits["amount"])
    debit_cp = list(debits["counterparty_id"])

    for _, credit in credits.iterrows():
        window_end = credit["timestamp"] + pd.Timedelta(minutes=PASS_THROUGH_WINDOW_MIN)
        for j, d_time in enumerate(debit_times):
            if d_time < credit["timestamp"] or d_time > window_end:
                continue
            if debit_cp[j] == credit["counterparty_id"]:
                continue  # same counterparty is not a pass-through
            if debit_amounts[j] < 0.5 * float(credit["amount"]):
                continue  # a small purchase is spending, not forwarding
            matched_amount += float(credit["amount"])
            forward_minutes.append((d_time - credit["timestamp"]).total_seconds() / 60)
            break

    avg_minutes = (
        sum(forward_minutes) / len(forward_minutes) if forward_minutes else 0.0
    )
    return matched_amount, total_credit, avg_minutes


def compute_account_features(account_id: str, account: pd.DataFrame) -> dict[str, Any]:
    account = account.sort_values("timestamp")
    days = max(account["date"].nunique(), 1)

    credits = account[account["direction"] == "credit"]
    debits = account[account["direction"] == "debit"]

    # Opening balance implied by the first recorded row.
    first = account.iloc[0]
    opening = (
        float(first["balance_after"]) - float(first["amount"])
        if first["direction"] == "credit"
        else float(first["balance_after"]) + float(first["amount"])
    )
    end_balance = float(account.iloc[-1]["balance_after"])
    total_credit = float(credits["amount"].sum())
    inflow = opening + total_credit
    retained_ratio = end_balance / inflow if inflow > 0 else 0.0

    matched_amount, total_credit_check, avg_forward = _pair_pass_through(account)
    pass_ratio = matched_amount / total_credit_check if total_credit_check else 0.0

    # Device/location unfamiliarity vs the account's early history.
    baseline = account.head(3)
    base_devices = set(baseline["device_id"])
    base_locations = set(baseline["location"])
    new_device_ratio = float((~account["device_id"].isin(base_devices)).mean())
    new_location_ratio = float((~account["location"].isin(base_locations)).mean())

    per_day = credits.groupby("date").size()
    max_daily_credits = int(per_day.max()) if not per_day.empty else 0

    return {
        "account_id": account_id,
        "txn_count": int(len(account)),
        "credit_count": int(len(credits)),
        "debit_count": int(len(debits)),
        "credits_per_day": round(len(credits) / days, 2),
        "unique_senders": int(credits["counterparty_id"].nunique()),
        "pass_through_ratio": round(pass_ratio, 3),
        "avg_forward_minutes": round(avg_forward, 1),
        "retained_ratio": round(retained_ratio, 3),
        "new_device_ratio": round(new_device_ratio, 3),
        "new_location_ratio": round(new_location_ratio, 3),
        "max_daily_credits": max_daily_credits,
        "median_credit_amount": round(float(credits["amount"].median()), 2)
        if not credits.empty
        else 0.0,
        "total_credit_amount": round(total_credit, 2),
        "total_debit_amount": round(float(debits["amount"].sum()), 2),
        "end_balance": round(end_balance, 2),
    }


# ---------------------------------------------------------------------------
# Scoring: Isolation Forest + transparent rules
# ---------------------------------------------------------------------------


def evaluate_rules(f: dict[str, Any]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []

    def add(name: str, **fmt: Any) -> None:
        weight, template = RULES[name]
        hits.append(
            {
                "rule": name,
                "points": weight,
                "detail": template.format(**fmt),
            }
        )

    if (
        f["pass_through_ratio"] >= 0.5
        and 0 < f["avg_forward_minutes"] <= 30
    ):
        add(
            "rapid_pass_through",
            pct=f"{f['pass_through_ratio'] * 100:.0f}%",
            avg=f"{f['avg_forward_minutes']:.0f}",
        )
    if f["unique_senders"] >= 8:
        add("many_unrelated_senders", n=f["unique_senders"])
    if f["retained_ratio"] <= 0.05:
        add("near_zero_retention", pct=f"{f['retained_ratio'] * 100:.1f}%")
    if f["new_device_ratio"] >= 0.5:
        add("unfamiliar_device", pct=f"{f['new_device_ratio'] * 100:.0f}%")
    if f["max_daily_credits"] >= 6:
        add("burst_credits", n=f["max_daily_credits"])
    return hits


def score_accounts(features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Isolation Forest over the feature matrix, blended with rule points."""
    from sklearn.ensemble import IsolationForest

    frame = pd.DataFrame(features).set_index("account_id")
    matrix = frame[MODEL_FEATURES].fillna(0.0)

    model = IsolationForest(
        n_estimators=200, contamination="auto", random_state=42, n_jobs=1
    )
    model.fit(matrix)
    raw = -model.decision_function(matrix)  # higher = more anomalous
    lo, hi = float(min(raw)), float(max(raw))
    span = (hi - lo) or 1.0

    ranked: list[dict[str, Any]] = []
    for account_id, row in frame.iterrows():
        account_features = row.to_dict()
        account_features["account_id"] = account_id

        model_score = round((float(raw[frame.index.get_loc(account_id)]) - lo) / span * 100, 1)
        hits = evaluate_rules(account_features)
        rule_score = min(100, sum(h["points"] for h in hits))
        final = round(0.6 * model_score + 0.4 * rule_score)

        if final >= FLAG_THRESHOLD:
            level = "high"
        elif final >= WATCH_THRESHOLD:
            level = "watch"
        else:
            level = "normal"

        ranked.append(
            {
                **account_features,
                "model_score": model_score,
                "rule_score": rule_score,
                "score": final,
                "level": level,
                "rule_hits": hits,
                "summary": _summarise(account_features, hits),
            }
        )

    ranked.sort(key=lambda a: (-a["score"], a["account_id"]))
    for i, account in enumerate(ranked, start=1):
        account["rank"] = i
    return ranked


def _summarise(f: dict[str, Any], hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "Routine student activity: no mule patterns detected."
    parts = [
        f"{f['credit_count']} credits from {f['unique_senders']} senders",
        f"{f['pass_through_ratio'] * 100:.0f}% forwarded out within "
        f"{PASS_THROUGH_WINDOW_MIN} min",
        f"{f['retained_ratio'] * 100:.0f}% of inflow retained",
    ]
    if f["new_device_ratio"] >= 0.5:
        parts.append("mostly on an unfamiliar device")
    return "Mule-like pattern: " + "; ".join(parts) + "."


# ---------------------------------------------------------------------------
# Public API used by FastAPI routes
# ---------------------------------------------------------------------------

_CACHE: dict[str, Any] = {"key": None, "accounts": None, "by_id": {}}


def _cache_key() -> str:
    ensure_data()
    stat = DATA_PATH.stat()
    return f"{stat.st_mtime_ns}:{stat.st_size}"


def _build() -> None:
    key = _cache_key()
    if _CACHE["accounts"] is not None and _CACHE["key"] == key:
        return
    df = load_transactions()
    features = [
        compute_account_features(account_id, group)
        for account_id, group in df.groupby("account_id")
    ]
    accounts = score_accounts(features)
    _CACHE["key"] = key
    _CACHE["accounts"] = accounts
    _CACHE["by_id"] = {a["account_id"]: a for a in accounts}
    _CACHE["frame"] = df


def get_anomalies() -> dict[str, Any]:
    """Ranked accounts + model metadata for GET /api/anomalies."""
    _build()
    accounts = _CACHE["accounts"]
    return {
        "banner": SYNTH_BANNER,
        "generated_from": str(DATA_PATH.name),
        "model": "IsolationForest(n_estimators=200, random_state=42) + rule features",
        "window_days": WINDOW_DAYS,
        "total_accounts": len(accounts),
        "flagged_accounts": sum(1 for a in accounts if a["level"] == "high"),
        "watch_accounts": sum(1 for a in accounts if a["level"] == "watch"),
        "flag_threshold": FLAG_THRESHOLD,
        "accounts": accounts,
    }


def _flow_series(account: pd.DataFrame) -> dict[str, Any]:
    """Aligned credit/debit buckets; hourly when the activity is short and hot.

    Both series are resampled onto one common time index so the chart's
    labels, credits and debits always have equal length.
    """
    span_days = max(
        (account["timestamp"].max() - account["timestamp"].min()).days, 1
    )
    grain = "hour" if span_days <= 3 else "day"
    freq, fmt = ("1h", "%d %b %H:%M") if grain == "hour" else ("1D", "%d %b")
    frame = account.set_index("timestamp").sort_index()

    index = pd.date_range(
        start=frame.index.min().floor(freq),
        end=frame.index.max(),
        freq=freq,
    )
    credits = (
        frame[frame["direction"] == "credit"]["amount"]
        .resample(freq)
        .sum()
        .reindex(index, fill_value=0.0)
    )
    debits = (
        frame[frame["direction"] == "debit"]["amount"]
        .resample(freq)
        .sum()
        .reindex(index, fill_value=0.0)
    )

    return {
        "grain": grain,
        "labels": [t.strftime(fmt) for t in index],
        "credits": [round(float(v), 2) for v in credits.values],
        "debits": [round(float(v), 2) for v in debits.values],
    }


def get_account_detail(account_id: str) -> Optional[dict[str, Any]]:
    """Breakdown + money-flow series for one account."""
    _build()
    account = _CACHE["by_id"].get(account_id)
    if account is None:
        return None
    txns = _CACHE["frame"]
    group = txns[txns["account_id"] == account_id]
    return {
        "banner": SYNTH_BANNER,
        **account,
        "flow": _flow_series(group),
    }
