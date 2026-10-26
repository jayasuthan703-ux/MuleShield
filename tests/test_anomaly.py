"""Tests for the bank-side anomaly module (app/anomaly.py).

These use the synthetic dataset written by data/generate_transactions.py:
200 normal student accounts plus 10 injected mule-like accounts that share a
phone number of behaviours (spray of small credits, rapid pass-through,
unfamiliar device, near-zero retention).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import anomaly  # noqa: E402

data = anomaly.get_anomalies()
accounts = data["accounts"]


def _is_mule(account_id: str) -> bool:
    return "mule" in account_id


def test_injected_mule_accounts_rank_near_the_top() -> None:
    """All 10 injected mules must land in the top 15 of 210 accounts."""
    mules = [a for a in accounts if _is_mule(a["account_id"])]
    assert len(mules) == anomaly.MULE_ACCOUNTS == 10

    ranked_ids = [a["account_id"] for a in accounts]
    top15 = set(ranked_ids[:15])

    missing = [m["account_id"] for m in mules if m["account_id"] not in top15]
    assert not missing, f"mules missing from top 15: {missing}"

    # Every mule is flagged, and mules sit strictly above the best normal.
    assert all(m["level"] == "high" for m in mules)
    assert all(m["score"] >= anomaly.FLAG_THRESHOLD for m in mules)
    best_normal = min(
        (a["score"] for a in accounts if not _is_mule(a["account_id"])), default=0
    )
    assert min(m["score"] for m in mules) > best_normal


def test_normal_accounts_are_not_flagged_high() -> None:
    """No honest student account should be flagged as high risk."""
    normals = [a for a in accounts if not _is_mule(a["account_id"])]
    assert len(normals) == anomaly.NORMAL_ACCOUNTS == 200

    flagged = [a["account_id"] for a in normals if a["level"] == "high"]
    assert flagged == [], f"normal accounts wrongly flagged high: {flagged}"


def test_mule_features_show_the_pass_through_pattern() -> None:
    """Injected mules exhibit the behaviours the generator aimed for."""
    for m in (a for a in accounts if _is_mule(a["account_id"])):
        f = m
        assert f["unique_senders"] >= 8, f["account_id"]
        assert f["pass_through_ratio"] >= 0.5, f["account_id"]
        assert f["avg_forward_minutes"] <= 30, f["account_id"]
        assert f["retained_ratio"] <= 0.05, f["account_id"]
        assert f["new_device_ratio"] >= 0.5, f["account_id"]

        rules = {h["rule"] for h in f["rule_hits"]}
        assert "rapid_pass_through" in rules
        assert "many_unrelated_senders" in rules
        assert "near_zero_retention" in rules

        assert f["summary"]
        assert 0 <= f["score"] <= 100


def test_score_is_blend_of_model_and_rules() -> None:
    """Final score = 0.6 * model + 0.4 * rules, and both parts are bounded."""
    for a in accounts:
        assert 0 <= a["model_score"] <= 100
        assert 0 <= a["rule_score"] <= 100
        expected = round(0.6 * a["model_score"] + 0.4 * a["rule_score"])
        assert a["score"] == expected
        assert a["level"] in {"high", "watch", "normal"}


def test_account_detail_includes_flow_series() -> None:
    """Detail endpoint returns a per-account flow series for the chart."""
    top = accounts[0]
    detail = anomaly.get_account_detail(top["account_id"])
    assert detail["account_id"] == top["account_id"]
    flow = detail["flow"]
    assert flow["grain"] in {"hour", "day"}
    assert len(flow["labels"]) == len(flow["credits"]) == len(flow["debits"])
    assert flow["labels"], "expected at least one bucket"
    assert sum(flow["credits"]) > 0
