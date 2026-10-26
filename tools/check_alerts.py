"""Dev check: seed the DB, inspect clusters, and print seed-text similarities.

Usage: python tools/check_alerts.py [--reseed]
"""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import clustering, db  # noqa: E402

db.init_db()
if "--reseed" in sys.argv:
    db.clear_reports()
    print("cleared all reports")
seeded = clustering.ensure_seeded()
print("seeded now:", seeded, "| total reports:", db.count_reports())

alerts = clustering.get_alerts()
print(
    f"clusters={len(alerts['clusters'])} active={alerts['active_alerts']} "
    f"watching={alerts['watching']} unmatched={alerts['unmatched_reports']} "
    f"threshold={alerts['similarity_threshold']} min_for_alert={alerts['min_for_alert']}"
)
for c in alerts["clusters"]:
    print(
        f"  [{c['cluster_id']}] count={c['count']} active={c['active']} "
        f"linked_by={c['linked_by']} masks={c['masked_indicators']} "
        f"tags={c['campus_tags']} first={c['first_seen']} last={c['last_seen']}"
    )

print("\n--- pairwise cosine similarity of seed texts ---")
texts = [t for _, _, t in clustering.SEED_REPORTS]
vecs = [clustering.vectorize(t) for t in texts]
for i in range(len(texts)):
    for j in range(i + 1, len(texts)):
        sim = clustering.cosine_similarity(vecs[i], vecs[j])
        if sim >= 0.15:
            print(f"  {i}-{j}: {sim:.3f} {'LINK' if sim >= clustering.SIMILARITY_THRESHOLD else ''}")

print("\n--- extraction demo (report 1) ---")
sample = clustering.extract_indicators(
    "Call +91 98765 43210 or mail easyjob@upifake, open "
    "https://bonus-offer.test/claim or DM @student_earns_fast / wa.me/9876543210"
)
for ind in sample:
    print(
        f"  {ind['type']:9s} mask={clustering.mask_indicator(ind['type'], ind['value']):32s} "
        f"hash={clustering.hash_indicator(ind['type'], ind['value'])}"
    )

print("\n--- DB privacy audit ---")
print("  raw-text columns present:", db.raw_text_columns())
row = db.list_reports()[0]
print("  stored keys:", sorted(row.keys()))
print("  any value equal to a seed text:", any(
    v == t for r in db.list_reports() for v in map(str, r.values()) for t in texts
))
