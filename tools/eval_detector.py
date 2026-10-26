"""Ad-hoc evaluation of app/detector.py against data/messages.csv (dev tool)."""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.detector import MODEL_INFO, analyze  # noqa: E402

rows = list(csv.DictReader(open("data/messages.csv", encoding="utf-8")))
print("model info:", MODEL_INFO)

dist: dict = defaultdict(Counter)
scores: dict = defaultdict(list)
for r in rows:
    res = analyze(r["text"])
    dist[r["label"]][res["level"]] += 1
    scores[r["label"]].append(res["risk_score"])

for lbl in ["mule_recruitment", "other_scam", "normal"]:
    s = scores[lbl]
    print(
        f"{lbl:18s} levels={dict(dist[lbl])} "
        f"mean={sum(s)/len(s):.1f} min={min(s)} max={max(s)}"
    )

print()
print("--- normal rows scoring >= 30 (potential false positives) ---")
for r in rows:
    if r["label"] == "normal":
        res = analyze(r["text"])
        if res["risk_score"] >= 30:
            names = [s["name"] for s in res["matched_signals"]]
            print(f"  [{res['risk_score']}] {r['text'][:75]} -> {names}")

print()
print("--- mule rows scoring < 65 (missed High) ---")
for r in rows:
    if r["label"] == "mule_recruitment":
        res = analyze(r["text"])
        if res["risk_score"] < 65:
            names = [s["name"] for s in res["matched_signals"]]
            print(f"  [{res['risk_score']}] {r['text'][:75]} -> {names}")

print()
print("--- edge cases ---")
empty = analyze("")
print("empty:", empty["risk_score"], empty["level"], empty["note"])
long = analyze("hello world " * 600)
over = analyze("x" * 6000)
print("long input note:", over["note"], "score:", over["risk_score"])
tamil_mule = analyze(
    "உங்க வங்கிக் கணக்கை எனக்கு சில நாட்கள் மட்டும் வாடகைக்கு கொடுங்க. "
    "பணம் வந்ததும் உடனே அனுப்பிடணும், கமிஷன் உண்டு. யாருக்கும் சொல்லாதீங்க."
)
print("tamil mule:", tamil_mule["risk_score"], tamil_mule["level"],
      [s["name"] for s in tamil_mule["matched_signals"]])
hinglish_mule = analyze(
    "Bhai account me paise aayenge aur turant forward kar dena, 10 percent "
    "tumhare liye. Experience ki zarurat nahi, do din ka kaam hai, "
    "kisi ko mat batana."
)
print("hinglish mule:", hinglish_mule["risk_score"], hinglish_mule["level"],
      [s["name"] for s in hinglish_mule["matched_signals"]])
