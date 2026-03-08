#!/usr/bin/env python3
"""
StorageRationalizer — Cleanup Verification Tool

Reads the latest cleanup_*.log, cross-references every TRASHED/DELETED entry
against duplicates.db, and confirms:
  1. The deleted file had a valid duplicate group with a keep_file_id.
  2. The keep copy was NOT itself deleted (action != 'deleted' in duplicate_members,
     and scan_error != 'DELETED_PHASE3' in manifest.db).

Outputs: reports/cleanup_verification.txt
"""

import re
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

BASE        = Path.home() / "Desktop" / "StorageRationalizer"
DUPES_DB    = BASE / "manifests" / "duplicates.db"
MANIFEST_DB = BASE / "manifests" / "manifest.db"
LOGS_DIR    = BASE / "logs"
REPORTS_DIR = BASE / "reports"

# Matches lines like:
#   [2026-03-08T15:50:28.012095+00:00] TRASHED onedrive FE7C8667ED2A37CF!112205 some filename.pdf
#   [2026-03-08T15:50:28.012095+00:00] DELETED icloud_photos UUID some filename.jpg
#   [2026-03-08T15:50:28.012095+00:00] TRASHED local /path/to/file → /Users/…/.Trash/file
#   [2026-03-08T15:50:28.012095+00:00] DELETED local /path/to/file
LOG_RE = re.compile(
    r'^\[(?P<ts>[^\]]+)\] (?P<verb>TRASHED|DELETED) (?P<source>\S+) (?P<rest>.+)$'
)


def find_latest_log() -> Path:
    logs = sorted(LOGS_DIR.glob("cleanup_*.log"))
    if not logs:
        raise FileNotFoundError(f"No cleanup_*.log files found in {LOGS_DIR}")
    return logs[-1]


def parse_log_entries(log_path: Path) -> list[dict]:
    """Parse every TRASHED/DELETED entry into structured dicts."""
    entries = []
    with open(log_path) as f:
        for line in f:
            m = LOG_RE.match(line.rstrip())
            if not m:
                continue
            verb   = m.group("verb")
            source = m.group("source")
            rest   = m.group("rest")

            if source in ("onedrive", "google_drive", "icloud_photos"):
                # Format: <cloud_file_id> <filename…>
                parts = rest.split(" ", 1)
                cloud_id = parts[0]
                filename = parts[1] if len(parts) > 1 else ""
                entries.append({
                    "verb": verb, "source": source,
                    "cloud_file_id": cloud_id,
                    "source_path": None,
                    "filename": filename,
                    "raw": line.rstrip(),
                })
            elif source == "local":
                # TRASHED local /path → /trash/path   OR   DELETED local /path
                if " → " in rest:
                    src_path = rest.split(" → ")[0]
                else:
                    src_path = rest
                entries.append({
                    "verb": verb, "source": source,
                    "cloud_file_id": None,
                    "source_path": src_path,
                    "filename": Path(src_path).name,
                    "raw": line.rstrip(),
                })
    return entries


def verify_entries(entries: list[dict]) -> tuple[list, list]:
    """
    For each entry, check duplicates.db + manifest.db.
    Returns (verified, flagged) lists — each item is a dict with details.
    """
    dconn = sqlite3.connect(str(DUPES_DB))
    dconn.row_factory = sqlite3.Row
    mconn = sqlite3.connect(str(MANIFEST_DB))
    mconn.row_factory = sqlite3.Row

    verified = []
    flagged  = []

    for entry in entries:
        source       = entry["source"]
        cloud_id     = entry["cloud_file_id"]
        source_path  = entry["source_path"]
        filename     = entry["filename"]

        # ── Step 1: find the duplicate_member row for this deleted file ──────
        if cloud_id:
            member = dconn.execute(
                "SELECT * FROM duplicate_members WHERE cloud_file_id = ?",
                (cloud_id,)
            ).fetchone()
        else:
            member = dconn.execute(
                "SELECT * FROM duplicate_members WHERE source_path = ?",
                (source_path,)
            ).fetchone()

        if member is None:
            flagged.append({**entry,
                "reason": "NOT_IN_DUPLICATES_DB — no duplicate_members row found"})
            continue

        group_id = member["group_id"]
        file_id  = member["file_id"]

        # ── Step 2: get the group and its keep_file_id ────────────────────────
        group = dconn.execute(
            "SELECT * FROM duplicate_groups WHERE group_id = ?",
            (group_id,)
        ).fetchone()

        if group is None:
            flagged.append({**entry,
                "reason": f"NO_GROUP — group_id {group_id} not found in duplicate_groups"})
            continue

        keep_file_id = group["keep_file_id"]

        if not keep_file_id:
            flagged.append({**entry,
                "reason": f"NO_KEEPER — group {group_id} has NULL keep_file_id"})
            continue

        if keep_file_id == file_id:
            # The "keep" copy was itself logged as deleted — self-referential problem
            flagged.append({**entry,
                "reason": f"KEEPER_IS_SELF — keep_file_id == this file's file_id ({file_id})"})
            continue

        # ── Step 3: check the keep copy was not deleted in duplicates.db ─────
        keep_member = dconn.execute(
            "SELECT * FROM duplicate_members WHERE file_id = ? AND group_id = ?",
            (keep_file_id, group_id)
        ).fetchone()

        if keep_member is None:
            flagged.append({**entry,
                "reason": f"KEEPER_MISSING — keep_file_id {keep_file_id} not in duplicate_members for group {group_id}"})
            continue

        if keep_member["action"] == "deleted":
            flagged.append({**entry,
                "reason": f"KEEPER_DELETED — keeper {keep_file_id} ({keep_member['source']}/{keep_member['filename']}) "
                          f"has action='deleted' in duplicate_members"})
            continue

        # ── Step 4: confirm keeper not marked DELETED_PHASE3 in manifest ─────
        manifest_keep = mconn.execute(
            "SELECT file_id, scan_error, source, filename FROM files WHERE file_id = ?",
            (keep_file_id,)
        ).fetchone()

        if manifest_keep and manifest_keep["scan_error"] == "DELETED_PHASE3":
            flagged.append({**entry,
                "reason": f"KEEPER_PURGED — keeper {keep_file_id} ({manifest_keep['source']}/{manifest_keep['filename']}) "
                          f"has scan_error=DELETED_PHASE3 in manifest.db"})
            continue

        # ── All checks passed ─────────────────────────────────────────────────
        verified.append({**entry,
            "group_id":     group_id,
            "keep_file_id": keep_file_id,
            "keep_source":  keep_member["source"],
            "keep_filename": keep_member["filename"],
            "confidence":   group["confidence"],
        })

    dconn.close()
    mconn.close()
    return verified, flagged


def write_report(log_path: Path, verified: list, flagged: list, entries: list) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "cleanup_verification.txt"

    now = datetime.now(timezone.utc).isoformat()
    total = len(entries)

    lines = [
        "=" * 72,
        "  StorageRationalizer — Cleanup Verification Report",
        f"  Generated : {now}",
        f"  Log file  : {log_path}",
        "=" * 72,
        "",
        "SUMMARY",
        "-------",
        f"  Total TRASHED/DELETED entries  : {total:>6,}",
        f"  Verified (keeper confirmed)    : {len(verified):>6,}",
        f"  Flagged  (problem found)       : {len(flagged):>6,}",
        "",
    ]

    # ── Verified breakdown by source ────────────────────────────────────────
    by_source: dict[str, int] = {}
    for v in verified:
        by_source[v["source"]] = by_source.get(v["source"], 0) + 1

    if verified:
        lines += ["VERIFIED FILES BY SOURCE", "------------------------"]
        for src, cnt in sorted(by_source.items(), key=lambda x: -x[1]):
            lines.append(f"  {src:<22} {cnt:>6,}")
        lines.append("")

    # ── Flagged detail ───────────────────────────────────────────────────────
    if flagged:
        lines += [
            "FLAGGED ENTRIES",
            "---------------",
            "  These files were deleted but could not be confirmed to have a",
            "  safe, intact keeper copy.  Manual review recommended.",
            "",
        ]
        reason_counts: dict[str, int] = {}
        for f in flagged:
            reason_key = f["reason"].split(" — ")[0]
            reason_counts[reason_key] = reason_counts.get(reason_key, 0) + 1

        lines += ["  Reason breakdown:"]
        for reason, cnt in sorted(reason_counts.items(), key=lambda x: -x[1]):
            lines.append(f"    {reason:<40} {cnt:>5,}")
        lines += ["", "  Detail (first 200 flagged):"]

        for i, f in enumerate(flagged[:200]):
            lines.append(f"  [{i+1:>4}] source={f['source']}  id={f.get('cloud_file_id') or f.get('source_path')}")
            lines.append(f"         file={f['filename']}")
            lines.append(f"         reason={f['reason']}")
            lines.append("")

        if len(flagged) > 200:
            lines.append(f"  … and {len(flagged) - 200} more (see full data in duplicates.db).")
            lines.append("")
    else:
        lines += ["FLAGGED ENTRIES", "---------------", "  None — all deletions verified OK.", ""]

    lines += [
        "=" * 72,
        "  END OF REPORT",
        "=" * 72,
    ]

    out.write_text("\n".join(lines) + "\n")
    return out


def main():
    log_path = find_latest_log()
    print(f"Log file : {log_path}")

    print("Parsing log entries…")
    entries = parse_log_entries(log_path)
    print(f"  Found {len(entries):,} TRASHED/DELETED entries")

    if not entries:
        print("Nothing to verify.")
        return

    print("Cross-referencing against duplicates.db + manifest.db…")
    verified, flagged = verify_entries(entries)

    out = write_report(log_path, verified, flagged, entries)
    print(f"\nReport written to: {out}")
    print(f"  Verified : {len(verified):,}")
    print(f"  Flagged  : {len(flagged):,}")
    if flagged:
        print("\n  *** FLAGGED ENTRIES FOUND — review the report ***")


if __name__ == "__main__":
    main()
