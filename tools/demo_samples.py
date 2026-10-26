"""Print and verify the 5 demo messages for the 3-minute walkthrough.

Each message is posted to /api/analyze (what the Home page does) so the
printed risk level matches what the demo audience will see.

Usage:  python tools/demo_samples.py            # analyze all 5
        python tools/demo_samples.py --report 4  # also POST #4 as a report
"""

from __future__ import annotations

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000"

# 1 & 2 & 3 match the three chips on the Home page (app/static/app.js SAMPLES).
# 4 is the report-demo message: its phone number matches the seeded active
#    cluster, so submitting it shows "matches other reports -> ACTIVE".
# 5 is a softer, harder-to-spot script, to show the detector is not binary.
SAMPLES = [
    (
        "1. English offer (chip: English offer)",
        "Hi! Part-time job for students. Money will come into your bank account "
        "and you just forward it to another account the same day. 10% commission "
        "for you. No experience needed, instant payout. It's just for a few days "
        "so keep it secret and don't tell anyone.",
    ),
    (
        "2. Tamil offer (chip: Tamil offer)",
        "உங்க வங்கிக் கணக்கை சில நாட்கள் மட்டும் எனக்கு வாடகைக்கு கொடுங்க. "
        "பணம் வந்ததும் உடனே அனுப்பிடணும், கமிஷன் தர்றேன். யாருக்கும் சொல்லாதீங்க.",
    ),
    (
        "3. Friendly chat (chip: Friendly chat)",
        "Hey, are you coming to the canteen at 1? I will pay for my thali now, "
        "send me your share whenever you get time.",
    ),
    (
        "4. WhatsApp job DM (report demo — phone matches seeded cluster)",
        "Hello! Earn Rs.5,000 daily from home, students preferred, no experience "
        "needed. Money will be credited to your bank account and you just "
        "transfer it onward the same day. 10% for you. Message on WhatsApp at "
        "9876543210. Limited seats — keep this between us.",
    ),
    (
        "5. Soft referral script (borderline — harder to spot)",
        "Hi, we're onboarding campus ambassadors for a payments startup. Simple "
        "verification: we'll send a small amount to your account, you pass it to "
        "our partner account and keep a bonus. Totally normal onboarding step, "
        "takes two minutes. Are you in?",
    ),
]


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    for title, text in SAMPLES:
        data = post("/api/analyze", {"text": text})
        signals = data.get("matched_signals") or []
        names = ", ".join(s["name"] for s in signals[:4]) or "none"
        print(f"{title}")
        print(f"    level={data['level']}  score={data['risk_score']}  "
              f"signals={len(signals)}: {names}")
        print(f"    text: {text}")
        print()

    if "--report" in sys.argv:
        idx = int(sys.argv[sys.argv.index("--report") + 1]) - 1
        _, text = SAMPLES[idx]
        data = post("/api/report", {"text": text, "campus_tag": "CSE"})
        print("report of sample", idx + 1, "->")
        print("   masks:", data.get("masked_indicators"))
        print("   ", data.get("message"))


if __name__ == "__main__":
    main()
