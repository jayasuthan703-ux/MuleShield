"""Dev check: score separation between injected mules and normal accounts."""
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import anomaly  # noqa: E402

data = anomaly.get_anomalies()
accounts = data["accounts"]
print(
    f"total={data['total_accounts']} flagged(high)={data['flagged_accounts']} "
    f"watch={data['watch_accounts']} threshold={data['flag_threshold']}"
)

mules = [a for a in accounts if "mule" in a["account_id"]]
normals = [a for a in accounts if "mule" not in a["account_id"]]
print(f"\nmule ranks: {[a['rank'] for a in mules]}")
print(f"mule scores: {[a['score'] for a in mules]}")
print(f"normal best rank: {normals[0]['rank']} score {normals[0]['score']} "
      f"(level {normals[0]['level']})")
print(f"top 15: {[(a['rank'], a['account_id'], a['score']) for a in accounts[:15]]}")

top15 = {a["account_id"] for a in accounts[:15]}
print(f"\nmules in top 15: {sum(1 for m in mules if m['account_id'] in top15)}/10")
print(f"normals flagged high: {sum(1 for n in normals if n['level'] == 'high')}")

sample = mules[0]
print(f"\nsample mule {sample['account_id']}:")
print(f"  model={sample['model_score']} rule={sample['rule_score']} score={sample['score']}")
for h in sample["rule_hits"]:
    print(f"  rule {h['rule']} (+{h['points']}): {h['detail']}")
print(f"  features: pass={sample['pass_through_ratio']} senders={sample['unique_senders']} "
      f"retained={sample['retained_ratio']} newdev={sample['new_device_ratio']} "
      f"avg_fwd={sample['avg_forward_minutes']} burst={sample['max_daily_credits']}")

worst = normals[0]
print(f"\ntop normal {worst['account_id']} (score {worst['score']}):")
for h in worst["rule_hits"]:
    print(f"  rule {h['rule']} (+{h['points']}): {h['detail']}")

detail = anomaly.get_account_detail(sample["account_id"])
flow = detail["flow"]
print(f"\nflow grain={flow['grain']} points={len(flow['labels'])}")
print(f"  first 3: {list(zip(flow['labels'][:3], flow['credits'][:3], flow['debits'][:3]))}")
