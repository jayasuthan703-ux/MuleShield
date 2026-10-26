"""Verify the exact messages that tests/test_detector.py will use."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detector import analyze  # noqa: E402

SCAM = (
    "Hi, part-time work for students - money will land in your bank account "
    "and you just forward it within 30 minutes. 10 percent commission for "
    "you, no experience needed and instant payout. It is only for a few days "
    "and your senior referred you, so keep this between us and don't tell "
    "anyone."
)
BENIGN = (
    "Hey, are you coming to the canteen at 1? I will pay for my thali now, "
    "send me your share whenever you get time."
)
TAMIL_SCAM = (
    "உங்க வங்கிக் கணக்கை சில நாட்கள் மட்டும் எனக்கு வாடகைக்கு கொடுங்க. "
    "பணம் வந்ததும் உடனே அனுப்பிடணும், கமிஷன் தர்றேன். யாருக்கும் சொல்லாதீங்க."
)

for name, msg in [("SCAM", SCAM), ("BENIGN", BENIGN), ("TAMIL_SCAM", TAMIL_SCAM)]:
    res = analyze(msg)
    print(f"{name}: score={res['risk_score']} level={res['level']} "
          f"rule={res['rule_score']} model={res['model_score']}")
    print("   signals:", [s["name"] for s in res["matched_signals"]])

# summary over full CSV after pattern tweaks
import csv  # noqa: E402
from collections import Counter, defaultdict  # noqa: E402

rows = list(csv.DictReader(open("data/messages.csv", encoding="utf-8")))
dist = defaultdict(Counter)
for r in rows:
    dist[r["label"]][analyze(r["text"])["level"]] += 1
print()
for lbl in ["mule_recruitment", "other_scam", "normal"]:
    print(lbl, dict(dist[lbl]))
