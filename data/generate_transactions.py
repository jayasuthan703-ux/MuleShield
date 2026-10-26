"""Generate synthetic student-account transactions for the bank dashboard.

This is the only place account/transaction data is invented. It writes
``data/transactions.csv``. Nothing here is real: the account ids, sender ids,
devices and locations are all fabricated, and no network access is used.

Shape of the data
-----------------
* ``NORMAL_ACCOUNTS`` "student" accounts with realistic low-and-slow activity:
  a salary/parent credit, small canteen/UPI debits, an occasional transfer to
  a friend. Money that comes in mostly stays in the account.
* ``MULE_ACCOUNTS`` injected mule-like accounts that show the classic
  pass-through pattern flagged by ``app/anomaly.py``:
    - many small credits from lots of *unrelated* senders,
    - each credit forwarded on within minutes,
    - a new device / new location that does not match the account's history,
    - near-zero balance retained at the end of the window.

Usage
-----
    python data/generate_transactions.py            # writes data/transactions.csv
    python data/generate_transactions.py --seed 7   # a different invented world

The generator is deterministic for a given seed, so the demo and the tests are
reproducible.
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

OUT_PATH = Path(__file__).resolve().parent / "transactions.csv"

NORMAL_ACCOUNTS = 200
MULE_ACCOUNTS = 10
WINDOW_DAYS = 30

#: End of the synthetic window; every timestamp falls on or before this.
WINDOW_END = datetime(2026, 10, 25, 23, 0, 0)

ROWS_HEADER = [
    "account_id",
    "timestamp",
    "direction",  # credit | debit
    "amount",
    "counterparty_id",
    "device_id",
    "location",
    "balance_after",
]

DEVICES = [f"dev-{i:03x}" for i in range(0x100, 0x140)]
LOCATIONS = [
    "chennai-campus",
    "chennai-hostel",
    "coimbatore",
    "madurai",
    "bengaluru",
    "online-unknown",
]

CATEGORIES = ["canteen", "recharge", "auto", "upi", "transfer", "atm"]


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def generate_normal_account(
    account_id: str, rng: random.Random, window_start: datetime
) -> list[dict]:
    """One honest student account: money in mostly stays put."""
    balance = float(rng.randrange(500, 15000, 50))
    device = rng.choice(DEVICES)
    location = rng.choice(LOCATIONS[:4])
    opened = window_start + timedelta(days=rng.uniform(0, 10))
    now = opened
    rows: list[dict] = []

    def emit(direction: str, amount: float, cp: str, at: datetime) -> None:
        nonlocal balance
        balance = balance + amount if direction == "credit" else balance - amount
        rows.append(
            {
                "account_id": account_id,
                "timestamp": _iso(at),
                "direction": direction,
                "amount": f"{amount:.2f}",
                "counterparty_id": cp,
                "device_id": device,
                "location": location,
                "balance_after": f"{balance:.2f}",
            }
        )

    # A monthly-ish income: parents or a part-time wage.
    if rng.random() < 0.85:
        emit("credit", rng.randrange(3000, 22000, 100), f"src-{rng.randrange(1000, 1012)}", now)

    n = rng.randrange(8, 26)
    for _ in range(n):
        now = now + timedelta(hours=rng.uniform(2, 30))
        if now > WINDOW_END:
            break
        if rng.random() < 0.22 and balance > 1500:
            # Occasionally send money to someone they know.
            emit("debit", rng.randrange(200, 4000, 50), f"frnd-{rng.randrange(900, 940)}", now)
        else:
            cat = rng.choice(CATEGORIES)
            emit("debit", rng.randrange(30, 700, 10), f"{cat}-{rng.randrange(500)}", now)
        # Keep the account solvent so it never looks drained.
        if balance < 300:
            emit("credit", rng.randrange(1000, 5000, 50), "topup-wallet", now + timedelta(hours=6))

    return rows


def generate_mule_account(
    account_id: str, rng: random.Random, window_start: datetime
) -> list[dict]:
    """One mule account: spray of small credits, forwarded on within minutes."""
    balance = float(rng.randrange(400, 2500, 50))
    home_device = rng.choice(DEVICES)
    burner_device = rng.choice([d for d in DEVICES if d != home_device])
    home_location = rng.choice(LOCATIONS[:4])
    rows: list[dict] = []

    def emit(at: datetime, direction: str, amount: float, cp: str,
             device: str, location: str) -> None:
        nonlocal balance
        balance = balance + amount if direction == "credit" else balance - amount
        rows.append(
            {
                "account_id": account_id,
                "timestamp": _iso(at),
                "direction": direction,
                "amount": f"{amount:.2f}",
                "counterparty_id": cp,
                "device_id": device,
                "location": location,
                "balance_after": f"{balance:.2f}",
            }
        )

    # Phase 1: a few days of ordinary activity on the real device, so the
    # account history has a genuine baseline before the burner shows up.
    now = window_start
    for _ in range(rng.randrange(3, 6)):
        now = now + timedelta(hours=rng.uniform(6, 26))
        cat = rng.choice(CATEGORIES)
        emit(now, "debit", rng.randrange(30, 500, 10),
             f"{cat}-{rng.randrange(500)}", home_device, home_location)

    # Phase 2: new device + new location, and the pass-through pattern starts.
    location = rng.choice(LOCATIONS[3:])
    for _ in range(rng.randrange(9, 16)):  # 9-15 separate "jobs" per mule
        credit_at = now + timedelta(hours=rng.uniform(1, 14))
        if credit_at > WINDOW_END:
            break
        # Many small credits from unrelated senders.
        for _ in range(rng.randrange(2, 6)):
            amount = float(rng.randrange(400, 4000, 50))
            cp = f"stranger-{rng.randrange(10000, 99999)}"
            emit(credit_at, "credit", amount, cp, burner_device, location)
        # Forward nearly all of it within a few minutes, to one collector.
        drain = balance * rng.uniform(0.92, 1.0)
        emit(
            credit_at + timedelta(minutes=rng.uniform(1, 20)),
            "debit",
            drain,
            f"collector-{rng.randrange(700, 720)}",
            burner_device,
            location,
        )
        now = credit_at

    return rows


def generate(seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    window_start = WINDOW_END - timedelta(days=WINDOW_DAYS)
    rows: list[dict] = []

    for i in range(NORMAL_ACCOUNTS):
        rows += generate_normal_account(f"acct-{1000 + i}", rng, window_start)

    for i in range(MULE_ACCOUNTS):
        rows += generate_mule_account(f"acct-mule-{i:02d}", rng, window_start)

    rows.sort(key=lambda r: (r["account_id"], r["timestamp"]))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args, _ = parser.parse_known_args()

    rows = generate(seed=args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=ROWS_HEADER)
        writer.writeheader()
        writer.writerows(rows)

    accounts = {r["account_id"] for r in rows}
    mules = {a for a in accounts if "mule" in a}
    print(f"Wrote {len(rows)} rows for {len(accounts)} accounts to {args.out}")
    print(f"  normal accounts: {len(accounts) - len(mules)}   mule accounts: {len(mules)}")


if __name__ == "__main__":
    main()
