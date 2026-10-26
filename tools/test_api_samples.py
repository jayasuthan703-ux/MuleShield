"""POST the three UI sample messages to /api/analyze and print results.

SAMPLES mirrors app/static/app.js so the HTTP checks exercise exactly the
text a demo user would send from the Home page.
"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"

# Keep in sync with SAMPLES in app/static/app.js
SAMPLES = {
    "en": (
        "Hi! Part-time job for students. Money will come into your bank account "
        "and you just forward it to another account the same day. 10% commission "
        "for you. No experience needed, instant payout. It's just for a few days "
        "so keep it secret and don't tell anyone."
    ),
    "ta": (
        "உங்க வங்கிக் கணக்கை சில நாட்கள் மட்டும் எனக்கு வாடகைக்கு கொடுங்க. "
        "பணம் வந்ததும் உடனே அனுப்பிடணும், கமிஷன் தர்றேன். யாருக்கும் சொல்லாதீங்க."
    ),
    "ok": (
        "Hey, are you coming to the canteen at 1? I will pay for my thali now, "
        "send me your share whenever you get time."
    ),
}

LABELS = {"en": "English offer", "ta": "Tamil offer", "ok": "Friendly chat"}


def post_analyze(text: str) -> dict:
    req = urllib.request.Request(
        f"{BASE}/api/analyze",
        data=json.dumps({"text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as res:
        assert res.status == 200, res.status
        return json.loads(res.read().decode("utf-8"))


def main() -> None:
    with urllib.request.urlopen(f"{BASE}/api/health", timeout=10) as res:
        print("health:", res.read().decode())

    for key, text in SAMPLES.items():
        out = post_analyze(text)
        names = [s["name"] for s in out["matched_signals"]]
        print(f"\n[{LABELS[key]}] score={out['risk_score']} level={out['level']} "
              f"signals={len(names)}")
        for n in names:
            print("   -", n)
        print("   privacy:", out["privacy_note"])

    empty = post_analyze("")
    print(f"\n[empty] score={empty['risk_score']} level={empty['level']} "
          f"note={empty['note']}")
    over = post_analyze("please forward the money " * 400)
    print(f"[6000 chars] score={over['risk_score']} level={over['level']} "
          f"note={over['note']}")


if __name__ == "__main__":
    main()
