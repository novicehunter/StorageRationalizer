#!/usr/bin/env python3
"""
StorageRationalizer — Financial Targets Tracker (STUB)

Tracks monthly storage subscription costs and savings progress.
See: docs/FINANCIAL_TARGETS.md

Status: STUB — implementation pending
"""

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB_PATH = BASE / "manifests" / "financial_tracker.db"

# Subscription costs (update these when actual costs are known)
COSTS = {
    "icloud_2tb": 9.99,
    "icloud_50gb": 0.99,
    "onedrive": 0.00,  # TODO: fill in actual cost
    "amazon_photos": 0.00,  # TODO: fill in actual cost
    "google_drive_2tb": 9.99,
}

TARGET_MONTHLY = 10.98  # Goal: iCloud 50GB + Google Drive 2TB


def init_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS snapshots (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            month       TEXT NOT NULL,
            icloud_gb   REAL,
            onedrive_gb REAL,
            gdrive_gb   REAL,
            active_subs TEXT,
            monthly_cost REAL,
            notes       TEXT,
            recorded_at TEXT NOT NULL
        )
    """
    )
    conn.commit()
    return conn


def cmd_status() -> None:
    """TODO: Query actual storage APIs for current usage."""
    print("Financial Tracker — Current Status")
    print("=" * 40)
    print("NOTE: This is a stub. Implement API queries to get live data.")
    print()
    print("Target monthly cost: ${:.2f}".format(TARGET_MONTHLY))
    print()
    print("Configured costs:")
    for service, cost in COSTS.items():
        print(f"  {service}: ${cost:.2f}/mo")


def cmd_snapshot(notes: str = "") -> None:
    """TODO: Auto-query storage sizes; for now prompts for manual input."""
    print("Recording monthly snapshot (manual entry):")
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    icloud_gb = float(input("iCloud current usage (GB): ") or 0)
    onedrive_gb = float(input("OneDrive current usage (GB): ") or 0)
    gdrive_gb = float(input("Google Drive current usage (GB): ") or 0)
    active_subs = input("Active subscriptions (comma-separated): ")
    monthly_cost = float(input("Current monthly total cost ($): ") or 0)

    conn = init_db()
    conn.execute(
        "INSERT INTO snapshots VALUES (NULL,?,?,?,?,?,?,?,?)",
        [
            month,
            icloud_gb,
            onedrive_gb,
            gdrive_gb,
            active_subs,
            monthly_cost,
            notes,
            datetime.now(timezone.utc).isoformat(),
        ],
    )
    conn.commit()
    print(f"Snapshot saved for {month}. Cost: ${monthly_cost:.2f}/mo")
    savings = monthly_cost - TARGET_MONTHLY
    if savings > 0:
        print(f"Still ${savings:.2f}/mo above target.")
    else:
        print(f"TARGET MET! Saving ${abs(savings):.2f}/mo vs target.")


def cmd_savings() -> None:
    """Show savings vs baseline."""
    conn = init_db()
    rows = conn.execute("SELECT month, monthly_cost FROM snapshots ORDER BY month").fetchall()
    if not rows:
        print("No snapshots recorded yet. Run --snapshot first.")
        return

    baseline = rows[0][1]
    print(f"{'Month':<12} {'Cost':>8} {'Savings vs Baseline':>22}")
    print("-" * 44)
    for month, cost in rows:
        savings = baseline - cost
        print(f"{month:<12} ${cost:>7.2f} ${savings:>21.2f}")

    latest = rows[-1][1]
    print()
    print(f"Target: ${TARGET_MONTHLY:.2f}/mo")
    print(f"Latest: ${latest:.2f}/mo")
    remaining = latest - TARGET_MONTHLY
    if remaining > 0:
        print(f"Still ${remaining:.2f}/mo to cut.")
    else:
        print("TARGET MET!")


def main() -> None:
    parser = argparse.ArgumentParser(description="StorageRationalizer financial tracker")
    parser.add_argument("--status", action="store_true", help="Show current cost status")
    parser.add_argument("--snapshot", action="store_true", help="Record monthly snapshot")
    parser.add_argument("--savings", action="store_true", help="Show savings over time")
    parser.add_argument("--notes", default="", help="Notes for this snapshot")
    args = parser.parse_args()

    if args.status:
        cmd_status()
    elif args.snapshot:
        cmd_snapshot(args.notes)
    elif args.savings:
        cmd_savings()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
