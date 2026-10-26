# MuleShield

Helps students recognise and refuse money-mule recruitment offers — and shows
the bank side of the same story. Built as a demo-ready local web app: FastAPI
backend, static HTML/vanilla-JS frontend, no build step, no network calls at
runtime, and **no real personal data anywhere**.

> Everything the app displays is synthetic or invented. The detector gives
> illustrative signals, not legal advice.

## Setup

1. **Python 3.11+** — check with `python --version`.
2. *(Recommended)* start from a clean environment so `requirements.txt` is
   the only source of truth:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate        # Windows
   # source .venv/bin/activate   # macOS/Linux
   ```

3. **Install dependencies** (everything is free and open source):

   ```bash
   pip install -r requirements.txt
   ```

4. **Run the server:**

   ```bash
   uvicorn app.main:app --reload
   ```

5. **Open http://127.0.0.1:8000/** — API health check at
   `http://127.0.0.1:8000/api/health`.

No API keys, no paid services, no CDNs. On first run the app generates what it
needs locally (synthetic transactions, SQLite DB, per-install salt); Chart.js is
vendored at `app/static/vendor/chart.umd.min.js` and the models fit at startup
on files in `data/`.

### First-run data

| File | Source |
|---|---|
| `data/messages.csv` | 150 invented sample messages (detector training/phrases) |
| `data/transactions.csv` | generated on first run by `data/generate_transactions.py` (deterministic, `--seed`) |
| `data/muleshield.db` | created by the app; holds only salted hashes + masked indicators (see Ethics) |
| `data/.indicator_salt` | per-install random salt, generated once |

Regenerate the synthetic world any time:

```bash
python data/generate_transactions.py --seed 42   # 200 normal + 10 mule accounts
python tools/check_alerts.py --reseed            # reset to the clean 10-report demo state
```

## What it does — six pages

1. **Home** — paste a recruitment message (or use a sample chip) and get a
   0–100 risk score, matched signals with highlighted snippets, a plain-language
   risk summary and recommended actions. Handles English and Tamil input,
   empty input (friendly inline error) and very long input (truncated at 5,000
   chars with a visible note).
2. **Simulator** — a 7-step walkthrough of a realistic recruitment attempt on
   timeline cards, with a "refuse and report" branch. Wording is factual and
   calm, labelled *Illustrative scenario, not legal advice.*
3. **Report** — paste what you received; the server extracts **indicators only**
   (phone, UPI id, URL, Telegram/WhatsApp handles), salted-hashes them, and
   clusters your report with others. Empty text → 400 with a friendly message;
   limit 7,000 chars. One button builds a redacted report summary for
   cybercrime.gov.in with personal fields left blank.
4. **Campus Alerts** — live clusters of matching reports. Three or more
   matching reports = **active alert**. Shows masked indicators only
   (`98xxxxxx10`, `ea***@upifake`, `bonus-offer.test/cl…`) plus campus tags and
   counts. Ships with ~10 seeded fake reports (3 clusters: 2 active, 1 watching).
5. **Bank Dashboard** — 200 synthetic student accounts scored for mule
   behaviour (Isolation Forest + transparent rules), ranked table, per-account
   score breakdown, rule cards in plain English, and a Chart.js money-flow
   chart. Permanent amber banner: **"Synthetic data for demonstration only."**
6. **Learn** — an 11-item red-flags checklist with live progress, a
   myth-vs-reality table (7 myths recruiters rely on), and a shareable
   **Campus Alert** text built from live masked data with a copy button
   (clipboard API + select-and-Ctrl+C fallback).

## Architecture

```
Browser (static SPA, hash routing: #/ #/simulator #/report #/alerts #/bank #/learn)
   │  fetch JSON
   ▼
FastAPI  app/main.py
   ├── POST /api/analyze            app/detector.py    rule blend + TF-IDF logistic model
   ├── POST /api/report             app/clustering.py  extract → mask → salt-hash → vectorise → store
   ├── GET  /api/alerts             app/clustering.py  union-find clusters, threshold = 3 → active
   ├── GET  /api/anomalies[/{id}]   app/anomaly.py     IsolationForest + 5 rules → ranked accounts
   └── static file mount            app/static/        index.html · app.js · styles.css · vendor/
                                                            │
                              app/db.py  ◄── SQLite (salted hashes, masked indicators, derived
                                             features only — raw text is never written to disk)
```

**Detector** (`app/detector.py`): `risk = 0.4 × rule_score + 0.6 × model_score`.
Rules catch secrecy/urgency/commission/forwarding phrasings; the model is a
TF-IDF + logistic blend fitted deterministically on `data/messages.csv` at
startup. Thresholds: High ≥ 65, Medium ≥ 30.

**Clustering** (`app/clustering.py`): indicators are masked for display and
salted-hashed (`data/.indicator_salt`) for matching; report text becomes a
sparse TF-IDF fingerprint. Two reports cluster when they share an indicator
hash or have cosine similarity ≥ 0.45. `MIN_FOR_ACTIVE_ALERT = 3`.

**Anomaly scoring** (`app/anomaly.py`): per-account features (credits/day,
pass-through ratio, unique senders, time-to-forward, retained balance, new
device/location share, burst credits) → `IsolationForest(n_estimators=200,
random_state=42)` plus 5 named rules; `score = 0.6 × model + 0.4 × rules`.
Flag ≥ 70, watch ≥ 45. On the seeded dataset all 10 injected mules rank
#1–10 of 210 (scores 87–100) and no honest account is flagged high.

**Frontend**: one `index.html`, one `app.js` (per-page modules + hash router),
one `styles.css` (dark navy/teal theme). Loading placeholders, empty states,
friendly errors, `aria-live` regions, `:focus-visible` outlines,
`prefers-reduced-motion` support, and a mobile layout tested at 438 px
(hamburger nav, stacked myth table, scrollable data tables).

## Sample messages — the 5-message demo set

Messages 1–3 are the built-in chips on the Home page (see
`SAMPLES` in `app/static/app.js`); 4–5 live in `tools/demo_samples.py`, which
prints all five with their live scores (`python tools/demo_samples.py`).

**1. English offer → High 98, 5 signals** *(chip: 🇬🇧 English offer)*

> Hi! Part-time job for students. Money will come into your bank account and
> you just forward it to another account the same day. 10% commission for you.
> No experience needed, instant payout. It's just for a few days so keep it
> secret and don't tell anyone.

**2. Tamil offer → High 93, 5 signals** *(chip: 🇮🇳 Tamil offer)*

> உங்க வங்கிக் கணக்கை சில நாட்கள் மட்டும் எனக்கு வாடகைக்கு கொடுங்க. பணம்
> வந்ததும் உடனே அனுப்பிடணும், கமிஷன் தர்றேன். யாருக்கும் சொல்லாதீங்க.

**3. Friendly chat → Low 17, 0 signals** *(chip: 💬 Friendly chat — the
false-positive control)*

> Hey, are you coming to the canteen at 1? I will pay for my thali now, send
> me your share whenever you get time.

**4. WhatsApp job DM → High 89, 4 signals** *(report demo — its phone number
`9876543210` matches the seeded active cluster, so submitting it on the Report
page shows "matches other reports → ACTIVE alert")*

> Hello! Earn Rs.5,000 daily from home, students preferred, no experience
> needed. Money will be credited to your bank account and you just transfer
> it onward the same day. 10% for you. Message on WhatsApp at 9876543210.
> Limited seats — keep this between us.

**5. Soft referral script → Medium 56, 2 signals** *(the borderline case:
reads like normal onboarding, still trips commission + forwarding)*

> Hi, we're onboarding campus ambassadors for a payments startup. Simple
> verification: we'll send a small amount to your account, you pass it to our
> partner account and keep a bonus. Totally normal onboarding step, takes two
> minutes. Are you in?

## 3-minute demo script

**0:00–0:20 — Home.** Paste the English sample → *High risk*. Point at the
highlighted snippets: "forward it", "10% commission", "keep it secret". Note
the privacy line: analysed only, never stored.

**0:20–0:50 — Simulator.** Step through the timeline: DM → job pitch → the
first "test transfer" → pressure. Take the *refuse and report* branch to show
the safe exit. "This is the decision the whole app is about."

**0:50–1:20 — Report → Alerts.** Submit a report with a phone number
(`9876543210`) → it matches existing reports and becomes an **ACTIVE** campus
alert. Open Campus Alerts: masked indicators only, three-or-more threshold,
then *Generate report summary* → redacted text ready for cybercrime.gov.in.

**1:20–2:00 — Bank Dashboard.** Scroll the 210-account ranking: the 10 mule
accounts sit at the top (87–100), the best honest account is #11 at 52. Click
a mule: model vs rule bars, the five rule cards in plain English, and the
money-flow chart — teal credits in, red debits out minutes later, balance
never keeps anything. Banner stays visible: *Synthetic data for demonstration
only.*

**2:00–2:30 — Learn.** Tick the checklist against the sample message (several
flags light up red), debunk two myths from the table, then copy the shareable
Campus Alert for a class group.

**2:30–3:00 — Close on privacy + honesty.** Raw text is never stored — only
salted hashes and masked indicators (run `python tools/check_alerts.py` for a
live DB audit). All data invented, no network calls, detector is a demo
heuristic, not legal advice.

## Tests

```bash
python -m pytest tests/ -q     # 21 passed
```

| File | Tests |
|---|---|
| `tests/test_detector.py` | 5 — scoring, thresholds, Tamil/empty/long input |
| `tests/test_clustering.py` | 4 — indicator extraction/masking, clustering threshold |
| `tests/test_api.py` | 5 — analyze, report (empty/7,000-char, no raw-text echo), alerts shape |
| `tests/test_anomaly.py` | 5 — injected mules rank in the top 15, no false highs, score blend, flow series |
| `tests/test_health.py` | 2 — health endpoint |

## Limitations

- **Demo-grade detection.** The detector is a rule + TF-IDF blend tuned on 150
  invented messages; recruiters rewrite scripts constantly. Scores are
  illustrative signals, not a verdict, and never legal advice.
- **Synthetic everything.** Transactions, accounts, senders and reports are
  generated or seeded. Real banking telemetry is messier: shared devices,
  family transfers and cash-in all blur the features used here.
- **Isolation Forest caveats.** Scores are relative to this 210-account batch
  (min-max normalised), so adding data re-ranks everything. No concept drift
  handling, no calibrated probabilities.
- **Clustering is heuristic.** Cosine ≥ 0.45 plus shared indicator hashes;
  paraphrases of the same campaign without a shared indicator can stay in
  separate clusters, and one widely-shared phone number can over-merge.
- **Single-user local app.** No auth, no rate limiting, SQLite file, one
  install salt. Fine for a laptop demo; not a deployment.
- **Not a reporting channel.** The app prepares a redacted summary; filing
  still happens on cybercrime.gov.in / 1930.

## Ethics & privacy design

**Purpose.** Awareness and triage for a real harm that targets students — not
surveillance. The app helps a recipient decide *not* to reply, and helps a
campus see patterns without reading anyone's messages.

**Data minimisation by construction.**

- Submitted message text is processed in memory and **never written anywhere**:
  no raw-text column exists in the schema (verifiable via
  `raw_text_columns()` / `tools/check_alerts.py --reseed` audit output).
- What *is* stored for a report: salted hashes of indicators, display masks
  like `98xxxxxx10`, a campus tag, a timestamp, and derived numeric features.
- The salt lives in `data/.indicator_salt` (generated per install). Without it,
  hashes cannot be linked across installs or reversed to raw indicators.
- Text similarity uses a sparse TF-IDF fingerprint, not the text itself.

**All data is invented.** No real phone numbers, names, accounts, UPI ids or
employers appear in code, seeds or datasets; the seeded reports use obviously
fake domains (`upifake`, `bonus-offer.test`). The bank dataset is generated
locally by a deterministic script.

**No exfiltration.** Zero third-party requests at runtime — no CDNs, fonts,
telemetry or paid APIs. Verified in-browser: 0 external requests across all
six pages.

**Honest framing.** Permanent banners and footers mark synthetic data and
illustrative-only advice; the report summary leaves personal fields blank and
points to official channels rather than pretending to be a filing.

**Anti-stigma.** Copy avoids blaming victims ("scripts written by
professionals"), and the myth table explicitly rejects the "only careless
people fall for this" framing.

## Structure

```
app/
  main.py          FastAPI app; serves app/static and the /api routes
  detector.py      Recruitment-message detector (rules + TF-IDF model)
  clustering.py    Indicator extraction/masking/hashing + report clustering
  anomaly.py       Bank-side anomaly scoring (IsolationForest + rules)
  db.py            SQLite access layer (no raw text, ever)
  static/          index.html · app.js · styles.css · vendor/chart.umd.min.js
data/
  messages.csv             150 invented sample messages
  generate_transactions.py deterministic synthetic transaction generator
  transactions.csv         generated (210 accounts, ~4,000 rows)
tests/             pytest suite (21 tests)
tools/             dev scripts: check_alerts, check_anomalies, smoke_endpoints,
                   demo_samples (5-message demo set), test_api_samples
```
