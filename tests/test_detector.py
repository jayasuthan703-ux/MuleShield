"""Tests for the hybrid recruitment-message detector (app/detector.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detector import MAX_TEXT_LENGTH, analyze  # noqa: E402

# A realistic mule-recruitment message that is NOT a verbatim row of
# data/messages.csv - it must generalise beyond the training examples.
SCAM_MESSAGE = (
    "Hi, part-time work for students - money will land in your bank account "
    "and you just forward it within 30 minutes. 10 percent commission for "
    "you, no experience needed and instant payout. It is only for a few days "
    "and your senior referred you, so keep this between us and don't tell "
    "anyone."
)

# Everyday student chat that mentions money/UPI innocently.
BENIGN_MESSAGE = (
    "Hey, are you coming to the canteen at 1? I will pay for my thali now, "
    "send me your share whenever you get time."
)


def test_known_scam_message_scores_high() -> None:
    result = analyze(SCAM_MESSAGE)

    assert result["level"] == "High"
    assert result["risk_score"] >= 65
    assert 0 <= result["risk_score"] <= 100

    # Rule engine must flag and explain the classic signals.
    names = [s["name"] for s in result["matched_signals"]]
    assert len(names) >= 3
    assert any("Commission" in n for n in names)
    assert any("Forward" in n for n in names)
    for signal in result["matched_signals"]:
        assert signal["snippet"]
        assert signal["explanation"]

    # Plain-language legal summary: no statute section numbers, points at
    # official sources, and says it is not legal advice.
    summary = result["legal_risk_summary"].lower()
    assert "not legal advice" in summary
    assert "official sources" in summary
    assert "section" not in summary

    assert result["recommended_actions"]


def test_benign_message_scores_low() -> None:
    result = analyze(BENIGN_MESSAGE)

    assert result["level"] == "Low"
    assert result["risk_score"] < 30
    # An everyday canteen/UPI chat must not trip any rule signal.
    assert result["matched_signals"] == []
    assert result["rule_score"] == 0
    assert result["recommended_actions"]


def test_non_english_tamil_mule_message_scores_high() -> None:
    tamil_scam = (
        "உங்க வங்கிக் கணக்கை சில நாட்கள் மட்டும் எனக்கு வாடகைக்கு கொடுங்க. "
        "பணம் வந்ததும் உடனே அனுப்பிடணும், கமிஷன் தர்றேன். யாருக்கும் சொல்லாதீங்க."
    )
    result = analyze(tamil_scam)

    assert result["level"] == "High"
    assert result["risk_score"] >= 65
    assert len(result["matched_signals"]) >= 3


def test_empty_input_is_handled() -> None:
    for empty in ("", "   ", None):
        result = analyze(empty)
        assert result["risk_score"] == 0
        assert result["level"] == "Low"
        assert result["matched_signals"] == []
        assert result["note"] == "empty_input"
        assert result["recommended_actions"]


def test_input_longer_than_5000_chars_is_truncated_not_crashed() -> None:
    long_text = "please forward the money " * 400  # > 5,000 chars
    assert len(long_text) > MAX_TEXT_LENGTH

    result = analyze(long_text)

    assert result["note"] == f"truncated_to_{MAX_TEXT_LENGTH}_chars"
    assert 0 <= result["risk_score"] <= 100
    assert result["level"] in {"Low", "Medium", "High"}
