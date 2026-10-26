"""MuleShield hybrid recruitment-message detector.

Two complementary signals are blended into one 0-100 risk score:

1. **Weighted rule engine** - nine hand-tuned signals with regex/keyword
   patterns covering English, Tamil (Unicode), Tanglish and Hinglish.
   Each signal carries a weight and a plain-language explanation.
2. **TF-IDF + logistic regression model** - trained once at startup from
   the synthetic ``data/messages.csv`` (labels: mule_recruitment,
   other_scam, normal). Word 1-2-grams plus character 3-5-grams so that
   transliterated Tanglish/Hinglish and Tamil script are both handled.

Privacy: ``analyze()`` never stores, logs or transmits the submitted text.
The text exists only as a local variable for the duration of the call.
There is no database write, no file write, and no network call anywhere in
this module.

This is a teaching aid, not legal advice: ``legal_risk_summary`` deliberately
quotes no statute section numbers and points the user at official sources.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_TEXT_LENGTH = 5_000
DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "messages.csv"

#: risk_score >= HIGH_THRESHOLD   -> "High"
#: risk_score >= MEDIUM_THRESHOLD -> "Medium"
#: below that                     -> "Low"
HIGH_THRESHOLD = 65
MEDIUM_THRESHOLD = 30

RULE_WEIGHT_IN_BLEND = 0.4
MODEL_WEIGHT_IN_BLEND = 0.6

#: Matching several *independent* signals is stronger evidence than any one
#: alone, so the summed rule weight is amplified by +20% per extra signal
#: (1 signal -> x1.0, 2 -> x1.2, 3 -> x1.4, 4+ -> x1.6).
MULTI_SIGNAL_AMPLIFICATION = 0.2
MAX_AMPLIFICATION = 1.6

#: How much a confident "other_scam" prediction contributes to the model
#: score. Phishing that is not mule recruitment is still worth flagging.
OTHER_SCAM_MODEL_FACTOR = 0.5

PRIVACY_NOTE = (
    "Your message is analysed in memory only - it is never stored, "
    "logged or sent anywhere."
)


# ---------------------------------------------------------------------------
# Rule engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Signal:
    """One weighted rule signal with a plain-language explanation."""

    name: str
    weight: int
    regex: str
    explanation: str
    pattern: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "pattern", re.compile(self.regex, re.IGNORECASE | re.UNICODE)
        )


RULE_SIGNALS: tuple[Signal, ...] = (
    Signal(
        name="Commission for receiving money",
        weight=15,
        regex=(
            r"\bcommission\b|கமிஷன்|கமிசன்|சதவீத|\byour cut\b|\bhissa\b"
            r"|\b\d{1,3}\s*%\s*(for you|yours?|as your cut)\b"
            r"|\bkeep (a |the |your )?(bonus|cut)\b"
        ),
        explanation=(
            "Offers you a cut or commission for letting money pass through "
            "your account. Paying an ordinary person a percentage to move "
            "funds is how mule networks hide the origin of stolen money."
        ),
    ),
    Signal(
        name="Renting or lending your account",
        weight=20,
        regex=(
            r"\b(rent|lend|leasing)\b.{0,60}\baccount\b"
            r"|\baccount\b.{0,60}\brent\b"
            r"|\baccount\b[\w\s'-]{0,30}\b(de do|dedo|kudunga)\b"
            r"|\baccount\b[\w\s'-]{0,40}எனக்கு\s*கொடு"
            r"|வாடகைக்கு\s*கொடு"
            r"|வங்கி\s*கணக்கை.{0,40}வாடகை"
            r"|\baccount\b.{0,40}rent-uku"
            r"|\baccount-a\b.{0,40}\brent\b"
        ),
        explanation=(
            "Asks you to rent or lend your bank/UPI account. The account "
            "stays in your name, so every rupee that moves through it is "
            "traced back to you - even though you never touched the money."
        ),
    ),
    Signal(
        name="Forwarding received money",
        weight=15,
        regex=(
            r"(money|payment|amount|funds|paise|paisa)[\w\s,.'-]{0,60}\bforward\b"
            r"|\bforward\b[\w\s,.'-]{0,60}(money|payment|amount|funds|account|transfer)\b"
            r"|\b(transfer|send|forward)\b[\w\s,.'-]{0,40}money (you|that) (have )?(receive|received)"
            r"|receive[\w\s,.'-]{0,60}(and|then)[\w\s,.'-]{0,40}(send|transfer|forward|pass)"
            r"|receive[\w\s,.'-]{0,60}forward|forward[\w\s,.'-]{0,60}receive"
            r"|pass it on the same day"
            r"|(money|amount)[\w\s,.'-]{0,60}(anuppi|forward)"
            r"|vandhadhum[\w\s,.'-]{0,40}(forward|anuppi)"
            r"|(வந்தா|வந்ததும்)[\w\s,.'-]{0,60}அனுப்ப|ஃபார்வேட்"
            r"|account me[\w\s,.'-]{0,60}(forward|bhej)"
            r"|(credited|deposited|added)[\w\s,.'-]{0,60}\baccount\b"
            r"[\w\s,.'-]{0,60}(transfer|send|pass|forward)"
            r"|\byou\b[\w\s,.'-]{0,20}(just\s+)?(pass|transfer|send)\b"
            r"[\w\s,.'-]{0,10}\b(it|them|the money)\b[\w\s,.'-]{0,20}"
            r"\b(on|onwards?|to)\b"
            r"|\btransfer\w*[\w\s,.'-]{0,20}\bonwards?\b"
        ),
        explanation=(
            "Wants you to receive money and immediately send it somewhere "
            "else. Passing funds through quickly to disguise where they "
            "came from is the core job of a money mule."
        ),
    ),
    Signal(
        name="No experience / instant payout",
        weight=12,
        regex=(
            r"\b(no|without)\s+(any\s+|prior\s+)?experience\b"
            r"|experience\s+(ki zarurat nahi|thevai illa)"
            r"|அனுபவம்\s*தேவையில்லை"
            r"|instant\s*(payout|payment|pay|credit|deposit)"
            r"|\bpaid instantly\b|\bpayout (is )?instant\b"
            r"|payout[\w\s-]{0,20}(today|aaj|turant)"
            r"|இன்ஸ்டன்ட்\s*பேமென்ட்"
            r"|aaj hi milega payout"
        ),
        explanation=(
            "Promises easy money with no experience and instant payment. "
            "Real part-time jobs have a process; instant cash for a trivial "
            "task usually means you are the product, not the employee."
        ),
    ),
    Signal(
        name="Urgency / act now",
        weight=8,
        regex=(
            r"\b(urgent(ly)?|immediately|right now|asap|tonight|by morning|"
            r"within \d+ (minutes?|hours?)|today itself|by today)\b"
            r"|\b(turant|fauran|jaldi(jaldi)?)\b"
            r"|ஜிடி|உடனே|அவசரம்"
        ),
        explanation=(
            "Pushes you to act immediately. Pressure and deadlines are used "
            "so you don't stop to think, check with anyone, or search the "
            "offer online."
        ),
    ),
    Signal(
        name="Secrecy - don't tell anyone",
        weight=15,
        regex=(
            r"(don'?t|do not|never|no need to) (tell|share|mention|inform)\b"
            r"[\w\s,.'-]{0,40}(anyone|somebody|others|parents|friends|family)"
            r"|keep (this|it) (a )?(secret|confidential|between us)"
            r"|stay between us|between us only|\bsecrecy\b"
            r"|yaarum solla(a|e)thinga|share pannathinga"
            r"|சொல்லாத|ரகசியமா|யாருக்கும்\s*சொல்ல"
            r"|kisi ko mat batana|mat bolna|chup chap"
        ),
        explanation=(
            "Tells you to hide it from family and friends. Legitimate work "
            "never requires secrecy - the instruction exists so nobody "
            "warns you before it's too late."
        ),
    ),
    Signal(
        name="Just a few days",
        weight=12,
        regex=(
            r"\bfew days\b|\bcouple of days\b|சில நாட்கள்|கொஞ்ச நாள்"
            r"|\bdo (char )?din\b|sirf do din"
        ),
        explanation=(
            "Minimises it as 'only a few days'. Even a few days of transfers "
            "can make your account part of a fraud investigation that drags "
            "on for months or years."
        ),
    ),
    Signal(
        name="Senior / friend referral pressure",
        weight=10,
        regex=(
            r"\byour senior\b|senior (student|from|is|runs)"
            r"|friend'?s senior|referral (program|programme|network)"
            r"|senior[\w\s,.'-]{0,30}(doing|kar raha|pannitu|pannitu irukaaru)"
            r"|சீனியர்|tumhara senior|senior dhaan"
        ),
        explanation=(
            "Uses a senior or friend to make the offer feel trusted. Peer "
            "pressure is a deliberate recruitment trick - and the senior may "
            "already be a victim being pushed to recruit more."
        ),
    ),
    Signal(
        name="Requests UPI PIN / OTP / ATM card",
        weight=20,
        regex=(
            r"\bUPI\s*PIN\b|\bOTP\b|\bATM\s*(card|pin)\b|\bCVV\b"
            r"|\bcard\s*(number|numbers|details?)\b|\bpin\s*(number|code)\b"
            r"|\bcard\b[\w\s,.'-]{0,15}\bdetails?\b"
            r"|கார்டு\s*(எண்|விவர)|பின்\s*எண்"
        ),
        explanation=(
            "Asks for your UPI PIN, OTP, ATM card or CVV. These exist for "
            "your use alone - sharing any of them hands someone full control "
            "of your money, with no way to undo the transfer."
        ),
    ),
)


def _find_signals(text: str) -> tuple[list[dict[str, Any]], int]:
    """Run the rule engine. Returns (matched signal dicts, rule score)."""
    matched: list[dict[str, Any]] = []
    for signal in RULE_SIGNALS:
        m = signal.pattern.search(text)
        if m:
            snippet = m.group(0).strip()
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            matched.append(
                {
                    "name": signal.name,
                    "snippet": snippet,
                    "explanation": signal.explanation,
                    "weight": signal.weight,
                }
            )
    matched.sort(key=lambda s: s["weight"], reverse=True)
    if matched:
        amplification = min(
            MAX_AMPLIFICATION,
            1.0 + MULTI_SIGNAL_AMPLIFICATION * (len(matched) - 1),
        )
        rule_score = min(100, int(round(sum(s["weight"] for s in matched) * amplification)))
    else:
        rule_score = 0
    return matched, rule_score


# ---------------------------------------------------------------------------
# Model: TF-IDF + logistic regression, trained at startup
# ---------------------------------------------------------------------------

#: Populated at import (i.e. server startup). ``None`` means rules-only mode
#: (for example when data/messages.csv is missing).
MODEL: Any = None
MODEL_INFO: dict[str, Any] = {"trained": False}


def _train_model() -> tuple[Any, dict[str, Any]]:
    if not DATA_FILE.exists():
        return None, {
            "trained": False,
            "reason": f"{DATA_FILE.name} not found - using rules only",
        }
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import FeatureUnion, Pipeline

        texts: list[str] = []
        labels: list[str] = []
        with DATA_FILE.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                text = (row.get("text") or "").strip()
                label = (row.get("label") or "").strip()
                if text and label:
                    texts.append(text)
                    labels.append(label)
        if len(set(labels)) < 2 or len(texts) < 10:
            return None, {"trained": False, "reason": "not enough labelled data"}

        pipeline = Pipeline(
            [
                (
                    "tfidf",
                    FeatureUnion(
                        [
                            (
                                "word",
                                TfidfVectorizer(
                                    ngram_range=(1, 2),
                                    sublinear_tf=True,
                                    token_pattern=r"(?u)\b\w+\b",
                                ),
                            ),
                            (
                                "char",
                                TfidfVectorizer(
                                    analyzer="char_wb",
                                    ngram_range=(3, 5),
                                    sublinear_tf=True,
                                ),
                            ),
                        ]
                    ),
                ),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=1000, class_weight="balanced", C=2.0
                    ),
                ),
            ]
        )
        pipeline.fit(texts, labels)
        return pipeline, {
            "trained": True,
            "samples": len(texts),
            "classes": list(pipeline.classes_),
            "features": "tfidf word(1,2) + char_wb(3,5)",
        }
    except Exception as exc:  # pragma: no cover - defensive fallback
        return None, {"trained": False, "reason": f"training failed: {exc}"}


MODEL, MODEL_INFO = _train_model()


def _model_score(text: str) -> Optional[float]:
    """0-100 model contribution, or None when no model is available."""
    if MODEL is None:
        return None
    proba = MODEL.predict_proba([text])[0]
    dist = dict(zip(MODEL.classes_, proba))
    p_mule = float(dist.get("mule_recruitment", 0.0))
    p_other = float(dist.get("other_scam", 0.0))
    return round(min(100.0, 100.0 * (p_mule + OTHER_SCAM_MODEL_FACTOR * p_other)), 1)


# ---------------------------------------------------------------------------
# Plain-language outputs
# ---------------------------------------------------------------------------


def _legal_summary(level: str) -> str:
    if level == "High":
        return (
            "This looks like the standard way students get recruited as money "
            "mules: your account would be used to move money that came from "
            "fraud, and the trail points straight back to your name. If you go "
            "along with it, your bank account and UPI access can be frozen, "
            "your own money can get stuck, and you may be questioned by the "
            "bank and the police even if you genuinely did not know what was "
            "happening - a freeze or a fraud record can also affect your "
            "ability to get loans or new accounts later. This is general "
            "information, not legal advice: rules vary by country and by "
            "case, so verify with official sources such as your bank, your "
            "college, or your national cybercrime reporting portal."
        )
    if level == "Medium":
        return (
            "This message carries several warning signs worth taking seriously, "
            "but it is not a clear-cut recruitment attempt. Treat any request "
            "to receive money and pass it on, or to share payment credentials, "
            "as a red flag until the sender is verified. The downside of "
            "getting this wrong - a frozen account and a fraud investigation "
            "in your name - is far larger than the reward being offered. This "
            "is general information, not legal advice; confirm anything "
            "suspicious with official sources such as your bank or your "
            "national cybercrime reporting portal."
        )
    return (
        "Nothing here strongly resembles a money-mule recruitment attempt, but "
        "scammers keep inventing new phrasing, so stay alert. Never share an "
        "OTP, UPI PIN, card details or passwords with anyone, and be "
        "suspicious of unexpected money that you are asked to pass on to "
        "someone else. This is general information, not legal advice; verify "
        "anything unusual directly with official sources such as your bank or "
        "your national cybercrime reporting portal."
    )


def _recommended_actions(level: str, signal_names: list[str]) -> list[str]:
    joined = " | ".join(signal_names).lower()

    if level == "High":
        actions = [
            "Do not reply to or engage with the sender - block them on the "
            "platform where you received this.",
            "Never share your OTP, UPI PIN, card details or passwords with "
            "anyone, for any reason.",
            "Do not receive or forward any money, even once; if funds have "
            "already arrived, contact your bank before doing anything else.",
            "Tell a parent, guardian or trusted college staff member exactly "
            "what you were asked to do.",
            "Report it to your national cybercrime portal (in India: "
            "cybercrime.gov.in) and your bank's official helpline.",
            "Keep a screenshot of the conversation as evidence.",
        ]
    elif level == "Medium":
        actions = [
            "Do not share OTP, UPI PIN, card details or passwords with anyone.",
            "Verify the sender through an independent, official channel "
            "before you respond.",
            "Do not click links or download attachments from this message.",
            "If they ask you to receive money and forward it, decline and "
            "tell a trusted adult.",
        ]
    else:
        actions = [
            "Continue as normal, but never share OTP, UPI PIN or card "
            "details with anyone.",
            "If an unexpected amount arrives in your account, do not spend "
            "or forward it - contact your bank first.",
        ]

    if "upi pin" in joined or "otp" in joined or "atm" in joined or "cvv" in joined:
        actions.insert(
            1,
            "Treat every OTP/PIN request as fraud: banks and wallet apps "
            "never ask for them, not even staff.",
        )
    if "secrecy" in joined or "don't tell anyone" in joined:
        actions.insert(
            -1,
            "Secrecy is the tell: show this message to someone you trust "
            "today.",
        )
    return actions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze(text: Any) -> dict[str, Any]:
    """Score a recruitment message. The text is never stored.

    Handles empty input and input longer than 5,000 characters (the first
    5,000 characters are analysed and a note is returned). Non-string input
    is coerced safely; non-Latin scripts are fully supported.
    """
    note: Optional[str] = None

    if text is None:
        text = ""
    elif not isinstance(text, str):
        text = str(text)

    if not text.strip():
        return {
            "risk_score": 0,
            "level": "Low",
            "matched_signals": [],
            "legal_risk_summary": (
                "There is nothing to analyse yet, so no risk can be assessed. "
                "This is general information, not legal advice; verify with "
                "official sources if you ever feel unsure."
            ),
            "recommended_actions": [
                "Paste or type the recruitment message you received, then "
                "run the check.",
            ],
            "rule_score": 0,
            "model_score": None,
            "note": "empty_input",
            "privacy_note": PRIVACY_NOTE,
        }

    if len(text) > MAX_TEXT_LENGTH:
        text = text[:MAX_TEXT_LENGTH]
        note = f"truncated_to_{MAX_TEXT_LENGTH}_chars"

    matched_signals, rule_score = _find_signals(text)
    score = _model_score(text)

    if score is None:
        risk_score = int(round(rule_score))
    else:
        risk_score = int(
            round(
                RULE_WEIGHT_IN_BLEND * rule_score
                + MODEL_WEIGHT_IN_BLEND * score
            )
        )
    risk_score = max(0, min(100, risk_score))

    if risk_score >= HIGH_THRESHOLD:
        level = "High"
    elif risk_score >= MEDIUM_THRESHOLD:
        level = "Medium"
    else:
        level = "Low"

    signal_names = [s["name"] for s in matched_signals]
    return {
        "risk_score": risk_score,
        "level": level,
        "matched_signals": matched_signals,
        "legal_risk_summary": _legal_summary(level),
        "recommended_actions": _recommended_actions(level, signal_names),
        "rule_score": rule_score,
        "model_score": score,
        "note": note,
        "privacy_note": PRIVACY_NOTE,
    }
