"""Smoke-test every MuleShield endpoint against a running server.

Usage: python tools/smoke_endpoints.py [base_url]
Default base_url: http://127.0.0.1:8000
Exits non-zero if any check fails.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
results: list[tuple[str, str, bool, str]] = []


def call(method: str, path: str, payload: dict | None = None) -> tuple[int, bytes]:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def check(label: str, method: str, path: str, payload: dict | None,
          want_status: int, verify) -> None:
    try:
        status, body = call(method, path, payload)
        if status != want_status:
            results.append((label, f"{method} {path}", False, f"status {status} != {want_status}"))
            return
        data = json.loads(body.decode("utf-8")) if body else {}
        note = verify(data) if verify else ""
        results.append((label, f"{method} {path}", True, note or f"{status}"))
    except Exception as exc:  # noqa: BLE001
        results.append((label, f"{method} {path}", False, f"{type(exc).__name__}: {exc}"))


def status_only(label: str, method: str, path: str, want: int) -> None:
    try:
        status, _ = call(method, path, None)
        results.append((label, f"{method} {path}", status == want, f"{status}"))
    except Exception as exc:  # noqa: BLE001
        results.append((label, f"{method} {path}", False, f"{type(exc).__name__}: {exc}"))


sys.stdout.reconfigure(encoding="utf-8")

# --- static pages -----------------------------------------------------------
status_only("index.html serves", "GET", "/", 200)
status_only("app.js serves", "GET", "/app.js", 200)
status_only("styles.css serves", "GET", "/styles.css", 200)
status_only("vendored Chart.js serves", "GET", "/vendor/chart.umd.min.js", 200)

# --- health -----------------------------------------------------------------
check("health", "GET", "/api/health", None, 200,
      lambda d: f"status={d.get('status')}")

# --- analyze ----------------------------------------------------------------
check("analyze: English scam", "POST", "/api/analyze",
      {"text": "Money will come into your bank account and you just forward it "
               "the same day. 10% commission, no experience needed, keep this secret."},
      200, lambda d: f"{d['level']} {d['risk_score']} signals={len(d['matched_signals'])}")

check("analyze: Tamil scam", "POST", "/api/analyze",
      {"text": "உங்க வங்கிக் கணக்கை சில நாட்கள் மட்டும் எனக்கு வாடகைக்கு கொடுங்க. "
               "பணம் வந்ததும் உடனே அனுப்பிடணும், கமிஷன் தர்றேன்."},
      200, lambda d: f"{d['level']} {d['risk_score']}")

check("analyze: benign", "POST", "/api/analyze",
      {"text": "Are you coming to the canteen at 1?"},
      200, lambda d: f"{d['level']} {d['risk_score']} signals={len(d['matched_signals'])}")

check("analyze: empty", "POST", "/api/analyze", {"text": ""}, 200,
      lambda d: f"note={d.get('note')}")

check("analyze: very long", "POST", "/api/analyze",
      {"text": "please forward the money " * 400}, 200,
      lambda d: f"note={d.get('note')}")

# --- report (valid + error paths) -------------------------------------------
check("report: indicators + campus tag", "POST", "/api/report",
      {"text": "Call me on 9876543210 or upi: demo99@upifake for part-time work "
               "at bonus-offer.test/claim. Keep it between us.",
       "campus_tag": "CSE"},
      200, lambda d: f"masks={d['masked_indicators']} msg={d['message'][:60]}")

check("report: empty rejected", "POST", "/api/report", {"text": ""}, 400,
      lambda d: f"detail={d.get('detail', '')[:50]}")

# --- alerts -----------------------------------------------------------------
check("alerts shape", "GET", "/api/alerts", None, 200,
      lambda d: f"reports={d['total_reports']} clusters={len(d['clusters'])} "
                f"active={d['active_alerts']} min_for_alert={d['min_for_alert']}")

# --- anomalies --------------------------------------------------------------
check("anomalies list", "GET", "/api/anomalies", None, 200,
      lambda d: f"banner={d['banner']!r} accounts={d['total_accounts']} "
                f"flagged={d['flagged_accounts']}")

check("anomalies: top account detail", "GET", "/api/anomalies/acct-mule-07", None, 200,
      lambda d: f"score={d['score']} level={d['level']} flow_buckets={len(d['flow']['labels'])}")

check("anomalies: unknown id 404", "GET", "/api/anomalies/acct-nope", None, 404,
      lambda d: f"detail={d.get('detail')}")

check("unknown api route 404", "GET", "/api/nope", None, 404, None)

# --- report -----------------------------------------------------------------
print(f"{'RESULT':<8} {'CHECK':<32} {'REQUEST'}")
print("-" * 78)
failed = 0
for label, req, ok, note in results:
    mark = "PASS" if ok else "FAIL"
    if not ok:
        failed += 1
    print(f"{mark:<8} {label:<32} {req:<34} {note}")
print("-" * 78)
print(f"{len(results) - failed}/{len(results)} passed")
sys.exit(1 if failed else 0)
