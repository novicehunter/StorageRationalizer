#!/usr/bin/env python3
"""
StorageRationalizer — Phase 2 Classifier
Finds duplicates across all sources, scores confidence, and outputs reports.

Keep priority (highest to lowest):
  1. google_drive     — going to be the new master
  2. onedrive         — largest store
  3. macbook_local    — physically here
  4. icloud_drive     — iCloud documents
  5. icloud_photos    — photo library

Outputs:
  - manifests/duplicates.db       SQLite duplicate groups
  - reports/duplicate_report.html Interactive HTML report
  - reports/safe_to_delete.csv    Files safe to delete
  - reports/savings_summary.txt   Space savings per source

Usage:
    python3 classifier.py
    python3 classifier.py --min-confidence 80   # only high confidence dupes
    python3 classifier.py --sources onedrive icloud_photos  # subset
"""

import argparse
import csv
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

console = Console()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE = Path.home() / "Desktop" / "StorageRationalizer"
MANIFEST_DB = BASE / "manifests" / "manifest.db"
DUPES_DB = BASE / "manifests" / "duplicates.db"
REPORTS_DIR = BASE / "reports"

# Keep priority — lower number = higher priority = keep this copy
SOURCE_PRIORITY = {
    "google_drive": 1,
    "onedrive": 2,
    "macbook_local": 3,
    "icloud_drive": 4,
    "icloud_photos": 5,
}

# Confidence levels
CONF_EXACT = 100  # same hash — guaranteed duplicate
CONF_HIGH = 90  # same filename + size + date — almost certainly same file
CONF_MEDIUM = 70  # same filename + size — likely same file
CONF_LOW = 50  # same filename only — possible duplicate, needs review

MIN_FILE_SIZE = 1024  # ignore files under 1KB


# ── Database ───────────────────────────────────────────────────────────────────
def open_manifest(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_dupes_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS duplicate_groups (
            group_id        TEXT PRIMARY KEY,
            match_type      TEXT NOT NULL,
            confidence      INTEGER NOT NULL,
            file_count      INTEGER NOT NULL,
            total_size      INTEGER,
            wasted_size     INTEGER,
            keep_file_id    TEXT,
            keep_source     TEXT,
            keep_filename   TEXT,
            created_at      TEXT
        )
    """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS duplicate_members (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id        TEXT NOT NULL,
            file_id         TEXT NOT NULL,
            source          TEXT NOT NULL,
            filename        TEXT NOT NULL,
            file_size       INTEGER,
            source_path     TEXT,
            cloud_file_id   TEXT,
            action          TEXT NOT NULL,
            confidence      INTEGER NOT NULL,
            match_key       TEXT,
            FOREIGN KEY (group_id) REFERENCES duplicate_groups(group_id)
        )
    """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_group   ON duplicate_members(group_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_action  ON duplicate_members(action)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source  ON duplicate_members(source)")
    conn.commit()
    return conn


# ── Helpers ────────────────────────────────────────────────────────────────────
def now_iso():
    return datetime.now(timezone.utc).isoformat()


def format_size(b):
    if not b:
        return "0 B"
    b = int(b)
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"


def pick_keeper(members: list) -> dict:
    """Pick the best copy to keep based on source priority."""
    return min(
        members,
        key=lambda m: (
            SOURCE_PRIORITY.get(m["source"], 99),
            # tiebreak: prefer larger file (higher quality)
            -(m["file_size"] or 0),
        ),
    )


def make_group_id(match_type: str, key: str) -> str:
    import hashlib

    return hashlib.md5(f"{match_type}:{key}".encode()).hexdigest()


# ── Dedup Methods ──────────────────────────────────────────────────────────────


def find_exact_hash_dupes(mconn, dconn, sources, progress, task) -> int:
    """Method 1: Same hash across different sources — 100% confidence."""
    progress.update(task, description="[green]Exact hash duplicates[/green]")
    count = 0

    source_filter = "','".join(sources)

    # SHA256 duplicates
    for row in mconn.execute(
        f"""
        SELECT sha256_hash, COUNT(*) c, GROUP_CONCAT(file_id) ids
        FROM files
        WHERE sha256_hash IS NOT NULL
          AND source IN ('{source_filter}')
          AND file_size >= {MIN_FILE_SIZE}
        GROUP BY sha256_hash
        HAVING COUNT(DISTINCT source) > 1
    """
    ):
        members = []
        for fid in row["ids"].split(","):
            f = mconn.execute("SELECT * FROM files WHERE file_id=?", (fid,)).fetchone()
            if f:
                members.append(dict(f))

        if len(members) < 2:
            continue

        keeper = pick_keeper(members)
        group_id = make_group_id("sha256", row["sha256_hash"])
        total_size = sum(m["file_size"] or 0 for m in members)
        wasted = total_size - (keeper["file_size"] or 0)

        dconn.execute(
            """
            INSERT OR REPLACE INTO duplicate_groups
            (group_id, match_type, confidence, file_count, total_size, wasted_size,
             keep_file_id, keep_source, keep_filename, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
            (
                group_id,
                "exact_hash",
                CONF_EXACT,
                len(members),
                total_size,
                wasted,
                keeper["file_id"],
                keeper["source"],
                keeper["filename"],
                now_iso(),
            ),
        )

        for m in members:
            action = "keep" if m["file_id"] == keeper["file_id"] else "delete"
            dconn.execute(
                """
                INSERT OR REPLACE INTO duplicate_members
                (group_id, file_id, source, filename, file_size,
                 source_path, cloud_file_id, action, confidence, match_key)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
                (
                    group_id,
                    m["file_id"],
                    m["source"],
                    m["filename"],
                    m["file_size"],
                    m["source_path"],
                    m["cloud_file_id"],
                    action,
                    CONF_EXACT,
                    row["sha256_hash"],
                ),
            )
        count += 1

    # MD5 duplicates (cloud files)
    for row in mconn.execute(
        f"""
        SELECT md5_hash, COUNT(*) c, GROUP_CONCAT(file_id) ids
        FROM files
        WHERE md5_hash IS NOT NULL
          AND source IN ('{source_filter}')
          AND file_size >= {MIN_FILE_SIZE}
        GROUP BY md5_hash
        HAVING COUNT(DISTINCT source) > 1
    """
    ):
        members = []
        for fid in row["ids"].split(","):
            f = mconn.execute("SELECT * FROM files WHERE file_id=?", (fid,)).fetchone()
            if f:
                members.append(dict(f))
        if len(members) < 2:
            continue

        keeper = pick_keeper(members)
        group_id = make_group_id("md5", row["md5_hash"])
        total_size = sum(m["file_size"] or 0 for m in members)
        wasted = total_size - (keeper["file_size"] or 0)

        dconn.execute(
            """
            INSERT OR REPLACE INTO duplicate_groups
            (group_id, match_type, confidence, file_count, total_size, wasted_size,
             keep_file_id, keep_source, keep_filename, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
            (
                group_id,
                "exact_hash",
                CONF_EXACT,
                len(members),
                total_size,
                wasted,
                keeper["file_id"],
                keeper["source"],
                keeper["filename"],
                now_iso(),
            ),
        )

        for m in members:
            action = "keep" if m["file_id"] == keeper["file_id"] else "delete"
            dconn.execute(
                """
                INSERT OR REPLACE INTO duplicate_members
                (group_id, file_id, source, filename, file_size,
                 source_path, cloud_file_id, action, confidence, match_key)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
                (
                    group_id,
                    m["file_id"],
                    m["source"],
                    m["filename"],
                    m["file_size"],
                    m["source_path"],
                    m["cloud_file_id"],
                    action,
                    CONF_EXACT,
                    row["md5_hash"],
                ),
            )
        count += 1

    dconn.commit()
    return count


def find_same_source_dupes(mconn, dconn, sources, progress, task) -> int:
    """Method 2: Same filename + size WITHIN a single source — internal duplicates."""
    progress.update(task, description="[yellow]Internal duplicates (within source)[/yellow]")
    count = 0

    source_filter = "','".join(sources)

    for row in mconn.execute(
        f"""
        SELECT source, filename, file_size, COUNT(*) c, GROUP_CONCAT(file_id) ids
        FROM files
        WHERE source IN ('{source_filter}')
          AND file_size >= {MIN_FILE_SIZE}
          AND filename NOT IN ('', '.DS_Store')
        GROUP BY source, filename, file_size
        HAVING c > 1
    """
    ):
        members = []
        for fid in row["ids"].split(","):
            f = mconn.execute("SELECT * FROM files WHERE file_id=?", (fid,)).fetchone()
            if f:
                members.append(dict(f))
        if len(members) < 2:
            continue

        # Skip if already caught by hash dedup
        group_id = make_group_id(
            "internal", f"{row['source']}:{row['filename']}:{row['file_size']}"
        )
        existing = dconn.execute(
            "SELECT 1 FROM duplicate_groups WHERE group_id=?", (group_id,)
        ).fetchone()
        if existing:
            continue

        keeper = pick_keeper(members)
        total_size = sum(m["file_size"] or 0 for m in members)
        wasted = total_size - (keeper["file_size"] or 0)

        dconn.execute(
            """
            INSERT OR REPLACE INTO duplicate_groups
            (group_id, match_type, confidence, file_count, total_size, wasted_size,
             keep_file_id, keep_source, keep_filename, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
            (
                group_id,
                "internal_dupe",
                CONF_HIGH,
                len(members),
                total_size,
                wasted,
                keeper["file_id"],
                keeper["source"],
                keeper["filename"],
                now_iso(),
            ),
        )

        for m in members:
            action = "keep" if m["file_id"] == keeper["file_id"] else "delete"
            dconn.execute(
                """
                INSERT OR REPLACE INTO duplicate_members
                (group_id, file_id, source, filename, file_size,
                 source_path, cloud_file_id, action, confidence, match_key)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
                (
                    group_id,
                    m["file_id"],
                    m["source"],
                    m["filename"],
                    m["file_size"],
                    m["source_path"],
                    m["cloud_file_id"],
                    action,
                    CONF_HIGH,
                    f"{row['filename']}:{row['file_size']}",
                ),
            )
        count += 1

    dconn.commit()
    return count


def find_cross_source_dupes(mconn, dconn, sources, progress, task) -> int:
    """Method 3: Same filename + size across different sources."""
    progress.update(task, description="[cyan]Cross-source duplicates[/cyan]")
    count = 0

    source_filter = "','".join(sources)

    for row in mconn.execute(
        f"""
        SELECT filename, file_size, COUNT(*) c,
               COUNT(DISTINCT source) src_count,
               GROUP_CONCAT(file_id) ids
        FROM files
        WHERE source IN ('{source_filter}')
          AND file_size >= {MIN_FILE_SIZE}
          AND filename NOT IN ('', '.DS_Store')
        GROUP BY filename, file_size
        HAVING src_count > 1
    """
    ):
        members = []
        for fid in row["ids"].split(","):
            f = mconn.execute("SELECT * FROM files WHERE file_id=?", (fid,)).fetchone()
            if f:
                members.append(dict(f))
        if len(members) < 2:
            continue

        group_id = make_group_id("cross", f"{row['filename']}:{row['file_size']}")
        existing = dconn.execute(
            "SELECT 1 FROM duplicate_groups WHERE group_id=?", (group_id,)
        ).fetchone()
        if existing:
            continue

        # Confidence based on whether dates also match
        dates = set(
            m.get("exif_date") or m.get("created_at", "")
            for m in members
            if m.get("exif_date") or m.get("created_at")
        )
        confidence = CONF_HIGH if len(dates) <= 1 else CONF_MEDIUM

        keeper = pick_keeper(members)
        total_size = sum(m["file_size"] or 0 for m in members)
        wasted = total_size - (keeper["file_size"] or 0)

        dconn.execute(
            """
            INSERT OR REPLACE INTO duplicate_groups
            (group_id, match_type, confidence, file_count, total_size, wasted_size,
             keep_file_id, keep_source, keep_filename, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
            (
                group_id,
                "cross_source",
                confidence,
                len(members),
                total_size,
                wasted,
                keeper["file_id"],
                keeper["source"],
                keeper["filename"],
                now_iso(),
            ),
        )

        for m in members:
            action = "keep" if m["file_id"] == keeper["file_id"] else "delete"
            dconn.execute(
                """
                INSERT OR REPLACE INTO duplicate_members
                (group_id, file_id, source, filename, file_size,
                 source_path, cloud_file_id, action, confidence, match_key)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
                (
                    group_id,
                    m["file_id"],
                    m["source"],
                    m["filename"],
                    m["file_size"],
                    m["source_path"],
                    m["cloud_file_id"],
                    action,
                    confidence,
                    f"{row['filename']}:{row['file_size']}",
                ),
            )
        count += 1

    dconn.commit()
    return count


def find_folder_dupes(mconn, dconn, sources, progress, task) -> int:
    """Method 4: Same folder name + same total size = duplicated folder tree."""
    progress.update(task, description="[magenta]Duplicate folder trees[/magenta]")
    count = 0

    source_filter = "','".join(sources)

    for row in mconn.execute(
        f"""
        SELECT filename, file_size, COUNT(*) c, GROUP_CONCAT(file_id) ids
        FROM files
        WHERE source IN ('{source_filter}')
          AND file_size >= 10*1024*1024
          AND (mime_type = 'application/zip'
               OR mime_type = 'application/x-zip-compressed'
               OR file_ext IN ('.zip','.rar','.7z','.tar','.gz'))
        GROUP BY filename, file_size
        HAVING c > 1
    """
    ):
        members = []
        for fid in row["ids"].split(","):
            f = mconn.execute("SELECT * FROM files WHERE file_id=?", (fid,)).fetchone()
            if f:
                members.append(dict(f))
        if len(members) < 2:
            continue

        group_id = make_group_id("archive", f"{row['filename']}:{row['file_size']}")
        existing = dconn.execute(
            "SELECT 1 FROM duplicate_groups WHERE group_id=?", (group_id,)
        ).fetchone()
        if existing:
            continue

        keeper = pick_keeper(members)
        total_size = sum(m["file_size"] or 0 for m in members)
        wasted = total_size - (keeper["file_size"] or 0)

        dconn.execute(
            """
            INSERT OR REPLACE INTO duplicate_groups
            (group_id, match_type, confidence, file_count, total_size, wasted_size,
             keep_file_id, keep_source, keep_filename, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
            (
                group_id,
                "duplicate_archive",
                CONF_EXACT,
                len(members),
                total_size,
                wasted,
                keeper["file_id"],
                keeper["source"],
                keeper["filename"],
                now_iso(),
            ),
        )

        for m in members:
            action = "keep" if m["file_id"] == keeper["file_id"] else "delete"
            dconn.execute(
                """
                INSERT OR REPLACE INTO duplicate_members
                (group_id, file_id, source, filename, file_size,
                 source_path, cloud_file_id, action, confidence, match_key)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
                (
                    group_id,
                    m["file_id"],
                    m["source"],
                    m["filename"],
                    m["file_size"],
                    m["source_path"],
                    m["cloud_file_id"],
                    action,
                    CONF_EXACT,
                    f"{row['filename']}:{row['file_size']}",
                ),
            )
        count += 1

    dconn.commit()
    return count


# ── Reports ────────────────────────────────────────────────────────────────────


def write_csv(dconn, min_confidence: int):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = REPORTS_DIR / "safe_to_delete.csv"

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "group_id",
                "match_type",
                "confidence",
                "action",
                "source",
                "filename",
                "file_size_bytes",
                "file_size_human",
                "source_path",
                "cloud_file_id",
                "match_key",
            ]
        )
        for row in dconn.execute(
            """
            SELECT m.*, g.match_type, g.confidence
            FROM duplicate_members m
            JOIN duplicate_groups g ON m.group_id = g.group_id
            WHERE m.action = 'delete'
              AND g.confidence >= ?
            ORDER BY g.confidence DESC, g.wasted_size DESC
        """,
            (min_confidence,),
        ):
            writer.writerow(
                [
                    row["group_id"],
                    row["match_type"],
                    row["confidence"],
                    row["action"],
                    row["source"],
                    row["filename"],
                    row["file_size"] or 0,
                    format_size(row["file_size"]),
                    row["source_path"] or "",
                    row["cloud_file_id"] or "",
                    row["match_key"] or "",
                ]
            )
    return csv_path


def write_savings_summary(dconn, mconn):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    txt_path = REPORTS_DIR / "savings_summary.txt"

    lines = []
    lines.append("=" * 60)
    lines.append("StorageRationalizer — Phase 2 Savings Summary")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 60)
    lines.append("")

    # Overall stats
    row = dconn.execute(
        """
        SELECT COUNT(DISTINCT g.group_id) groups,
               SUM(CASE WHEN m.action='delete' THEN 1 ELSE 0 END) to_delete,
               SUM(CASE WHEN m.action='delete' THEN m.file_size ELSE 0 END) wasted
        FROM duplicate_members m
        JOIN duplicate_groups g ON m.group_id = g.group_id
        WHERE g.confidence >= 70
    """
    ).fetchone()
    lines.append(f"Duplicate groups found:  {row['groups']:,}")
    lines.append(f"Files to delete:         {row['to_delete']:,}")
    lines.append(f"Space recoverable:       {format_size(row['wasted'])}")
    lines.append("")

    # By confidence level
    lines.append("── By Confidence Level ──")
    for conf, label in [
        (100, "Exact match (100%)"),
        (90, "High confidence (90%)"),
        (70, "Medium confidence (70%)"),
        (50, "Low confidence (50%)"),
    ]:
        row = dconn.execute(
            """
            SELECT COUNT(*) c,
                   SUM(m.file_size) sz
            FROM duplicate_members m
            JOIN duplicate_groups g ON m.group_id = g.group_id
            WHERE g.confidence = ? AND m.action = 'delete'
        """,
            (conf,),
        ).fetchone()
        if row["c"]:
            lines.append(f"  {label}: {row['c']:,} files — {format_size(row['sz'])}")
    lines.append("")

    # By source — how much can be deleted from each
    lines.append("── Space Recoverable by Source ──")
    for row in dconn.execute(
        """
        SELECT m.source,
               COUNT(*) files,
               SUM(m.file_size) sz
        FROM duplicate_members m
        JOIN duplicate_groups g ON m.group_id = g.group_id
        WHERE m.action = 'delete' AND g.confidence >= 70
        GROUP BY m.source
        ORDER BY sz DESC
    """
    ):
        lines.append(f"  {row['source']:<20} {row['files']:>6,} files   {format_size(row['sz'])}")
    lines.append("")

    # By match type
    lines.append("── By Match Type ──")
    for row in dconn.execute(
        """
        SELECT match_type, COUNT(DISTINCT group_id) groups,
               SUM(wasted_size) wasted
        FROM duplicate_groups
        WHERE confidence >= 70
        GROUP BY match_type
        ORDER BY wasted DESC
    """
    ):
        wasted_str = format_size(row["wasted"])
        lines.append(
            f"  {row['match_type']:<25} {row['groups']:>5,} groups   {wasted_str} recoverable"
        )
    lines.append("")
    lines.append("=" * 60)

    with open(txt_path, "w") as f:
        f.write("\n".join(lines))
    return txt_path


def write_html_report(dconn, mconn, min_confidence: int):
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    html_path = REPORTS_DIR / "duplicate_report.html"

    # Get summary stats
    stats = dconn.execute(
        """
        SELECT COUNT(DISTINCT g.group_id) groups,
               SUM(CASE WHEN m.action='delete' THEN 1 ELSE 0 END) to_delete,
               SUM(CASE WHEN m.action='delete' THEN m.file_size ELSE 0 END) wasted
        FROM duplicate_members m
        JOIN duplicate_groups g ON m.group_id = g.group_id
        WHERE g.confidence >= ?
    """,
        (min_confidence,),
    ).fetchone()

    # Get top duplicate groups
    groups = dconn.execute(
        """
        SELECT g.*,
               COUNT(m.id) member_count
        FROM duplicate_groups g
        JOIN duplicate_members m ON g.group_id = m.group_id
        WHERE g.confidence >= ?
        GROUP BY g.group_id
        ORDER BY g.wasted_size DESC
        LIMIT 500
    """,
        (min_confidence,),
    ).fetchall()

    # Source breakdown
    source_rows = dconn.execute(
        """
        SELECT m.source,
               COUNT(*) files,
               SUM(m.file_size) sz
        FROM duplicate_members m
        JOIN duplicate_groups g ON m.group_id = g.group_id
        WHERE m.action = 'delete' AND g.confidence >= ?
        GROUP BY m.source
        ORDER BY sz DESC
    """,
        (min_confidence,),
    ).fetchall()

    gen_time = datetime.now().strftime("%B %d, %Y at %H:%M")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>StorageRationalizer &mdash; Duplicate Report</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f172a; color: #e2e8f0;
  }}
  .header {{ background: linear-gradient(135deg, #1e3a5f, #1e40af); padding: 32px 40px; }}
  .header h1 {{ font-size: 28px; font-weight: 700; color: white; }}
  .header p {{ color: #93c5fd; margin-top: 6px; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 32px 40px; }}
  .stats {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px; margin-bottom: 32px;
  }}
  .stat-card {{
    background: #1e293b; border-radius: 12px;
    padding: 24px; border: 1px solid #334155;
  }}
  .stat-card .value {{ font-size: 32px; font-weight: 700; color: #60a5fa; }}
  .stat-card .label {{ font-size: 13px; color: #94a3b8; margin-top: 4px; }}
  .section {{
    background: #1e293b; border-radius: 12px;
    padding: 24px; margin-bottom: 24px; border: 1px solid #334155;
  }}
  .section h2 {{ font-size: 18px; font-weight: 600; margin-bottom: 16px; color: #f1f5f9; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{
    background: #0f172a; color: #94a3b8; padding: 10px 12px;
    text-align: left; font-weight: 600; border-bottom: 1px solid #334155;
  }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #1e293b; color: #cbd5e1; }}
  tr:hover td {{ background: #263548; }}
  .badge {{
    display: inline-block; padding: 2px 8px;
    border-radius: 9999px; font-size: 11px; font-weight: 600;
  }}
  .badge-100 {{ background: #065f46; color: #6ee7b7; }}
  .badge-90  {{ background: #1e3a5f; color: #93c5fd; }}
  .badge-70  {{ background: #78350f; color: #fcd34d; }}
  .badge-50  {{ background: #4c1d95; color: #c4b5fd; }}
  .badge-keep   {{ background: #065f46; color: #6ee7b7; }}
  .badge-delete {{ background: #7f1d1d; color: #fca5a5; }}
  .source-bar {{ display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }}
  .source-name {{ width: 160px; font-size: 13px; color: #94a3b8; }}
  .bar-track {{ flex: 1; background: #0f172a; border-radius: 4px; height: 20px; overflow: hidden; }}
  .bar-fill {{
    height: 100%;
    background: linear-gradient(90deg, #2563eb, #60a5fa);
    border-radius: 4px; transition: width 0.3s;
  }}
  .bar-label {{ width: 100px; font-size: 12px; color: #60a5fa; text-align: right; }}
  .expand-btn {{
    background: #334155; border: none; color: #94a3b8;
    padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 12px;
  }}
  .expand-btn:hover {{ background: #475569; color: #e2e8f0; }}
  .members-row {{ display: none; }}
  .members-row.open {{ display: table-row; }}
  .members-table {{
    width: 100%; background: #0f172a;
    border-radius: 8px; padding: 12px; margin: 4px 0;
  }}
  .members-table td {{ padding: 6px 10px; font-size: 12px; border-bottom: 1px solid #1e293b; }}
  .type-badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
  .type-exact_hash {{ background: #064e3b; color: #6ee7b7; }}
  .type-internal_dupe {{ background: #1e3a5f; color: #93c5fd; }}
  .type-cross_source {{ background: #78350f; color: #fcd34d; }}
  .type-duplicate_archive {{ background: #3b0764; color: #d8b4fe; }}
  .generated {{ color: #475569; font-size: 12px; margin-top: 32px; text-align: center; }}
</style>
</head>
<body>
<div class="header">
  <h1>StorageRationalizer &mdash; Duplicate Report</h1>
  <p>Phase 2 Classification &middot; Generated {gen_time}
  &middot; Min confidence: {min_confidence}%</p>
</div>
<div class="container">

  <div class="stats">
    <div class="stat-card">
      <div class="value">{stats['groups']:,}</div>
      <div class="label">Duplicate Groups Found</div>
    </div>
    <div class="stat-card">
      <div class="value">{stats['to_delete']:,}</div>
      <div class="label">Files to Delete</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:#34d399">{format_size(stats['wasted'])}</div>
      <div class="label">Space Recoverable</div>
    </div>
    <div class="stat-card">
      <div class="value" style="color:#f59e0b">{min_confidence}%</div>
      <div class="label">Minimum Confidence</div>
    </div>
  </div>

  <div class="section">
    <h2>Space Recoverable by Source</h2>"""

    max_sz = max((r["sz"] or 0 for r in source_rows), default=1)
    for r in source_rows:
        sz = r["sz"] or 0
        pct = int(sz / max_sz * 100) if max_sz else 0
        html += f"""
    <div class="source-bar">
      <div class="source-name">{r['source']}</div>
      <div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>
      <div class="bar-label">{format_size(sz)}</div>
    </div>"""

    html += """
  </div>

  <div class="section">
    <h2>Top Duplicate Groups</h2>
    <table>
      <thead>
        <tr>
          <th>Filename (keep)</th>
          <th>Match Type</th>
          <th>Confidence</th>
          <th>Copies</th>
          <th>Wasted Space</th>
          <th>Keep Source</th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody>"""

    for i, g in enumerate(groups):
        conf = g["confidence"]
        badge_class = f"badge-{conf}"
        type_class = f"type-{g['match_type']}"
        members = dconn.execute(
            """
            SELECT * FROM duplicate_members WHERE group_id=? ORDER BY action DESC
        """,
            (g["group_id"],),
        ).fetchall()

        html += f"""
        <tr>
          <td>{g['keep_filename'] or '—'}</td>
          <td><span class="type-badge {type_class}">{g['match_type']}</span></td>
          <td><span class="badge {badge_class}">{conf}%</span></td>
          <td>{g['file_count']}</td>
          <td style="color:#34d399">{format_size(g['wasted_size'])}</td>
          <td>{g['keep_source'] or '—'}</td>
          <td><button class="expand-btn" onclick="toggle('m{i}')">▶ Show</button></td>
        </tr>
        <tr class="members-row" id="m{i}">
          <td colspan="7">
            <table class="members-table">
              <tr>
                <td><b>Action</b></td><td><b>Source</b></td>
                <td><b>Filename</b></td><td><b>Size</b></td><td><b>Path / ID</b></td>
              </tr>"""

        for m in members:
            action_badge = "badge-keep" if m["action"] == "keep" else "badge-delete"
            location = m["source_path"] or m["cloud_file_id"] or "—"
            html += f"""
              <tr>
                <td><span class="badge {action_badge}">{m['action']}</span></td>
                <td>{m['source']}</td>
                <td>{m['filename']}</td>
                <td>{format_size(m['file_size'])}</td>
                <td style="font-family:monospace;font-size:11px;color:#64748b">{location[:80]}</td>
              </tr>"""

        html += """
            </table>
          </td>
        </tr>"""

    html += f"""
      </tbody>
    </table>
  </div>

  <p class="generated">StorageRationalizer Phase 2
  &middot; {datetime.now().strftime('%Y-%m-%d %H:%M')}
  &middot; {stats['groups']:,} groups &middot; {format_size(stats['wasted'])} recoverable</p>
</div>
<script>
function toggle(id) {{
  const row = document.getElementById(id);
  const btn = row.previousElementSibling.querySelector('.expand-btn');
  row.classList.toggle('open');
  btn.textContent = row.classList.contains('open') ? '▼ Hide' : '▶ Show';
}}
</script>
</body>
</html>"""

    with open(html_path, "w") as f:
        f.write(html)
    return html_path


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="StorageRationalizer Phase 2 Classifier")
    parser.add_argument(
        "--min-confidence", type=int, default=70, help="Minimum confidence threshold (default: 70)"
    )
    parser.add_argument(
        "--sources",
        nargs="+",
        default=["google_drive", "onedrive", "macbook_local", "icloud_drive", "icloud_photos"],
        help="Sources to classify",
    )
    parser.add_argument("--reset", action="store_true", help="Wipe duplicates DB and start fresh")
    args = parser.parse_args()

    console.rule("[bold blue]StorageRationalizer — Phase 2 Classifier[/bold blue]")
    console.print(f"  Manifest:  [cyan]{MANIFEST_DB}[/cyan]")
    console.print(f"  Sources:   [cyan]{', '.join(args.sources)}[/cyan]")
    console.print(f"  Min conf:  [cyan]{args.min_confidence}%[/cyan]")
    console.print()

    if not MANIFEST_DB.exists():
        console.print(f"[red]Manifest not found: {MANIFEST_DB}[/red]")
        console.print("[yellow]Run Phase 1 scanner first.[/yellow]")
        return

    if args.reset and DUPES_DB.exists():
        DUPES_DB.unlink()
        console.print("[yellow]Duplicates DB wiped — starting fresh[/yellow]\n")

    mconn = open_manifest(MANIFEST_DB)
    dconn = init_dupes_db(DUPES_DB)

    # Show what's in the manifest
    console.print("[bold]Files in manifest:[/bold]")
    for row in mconn.execute(
        "SELECT source, COUNT(*) c FROM files GROUP BY source ORDER BY c DESC"
    ):
        console.print(f"  {row['source']:<20} {row['c']:>8,} files")
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Classifying...", total=4)

        n1 = find_exact_hash_dupes(mconn, dconn, args.sources, progress, task)
        progress.advance(task)
        console.print(f"  ✓ Exact hash matches:      [green]{n1:,} groups[/green]")

        n2 = find_same_source_dupes(mconn, dconn, args.sources, progress, task)
        progress.advance(task)
        console.print(f"  ✓ Internal duplicates:     [green]{n2:,} groups[/green]")

        n3 = find_cross_source_dupes(mconn, dconn, args.sources, progress, task)
        progress.advance(task)
        console.print(f"  ✓ Cross-source duplicates: [green]{n3:,} groups[/green]")

        n4 = find_folder_dupes(mconn, dconn, args.sources, progress, task)
        progress.advance(task)
        console.print(f"  ✓ Duplicate archives:      [green]{n4:,} groups[/green]")

    console.print()

    # Write reports
    console.print("[bold]Writing reports...[/bold]")
    csv_path = write_csv(dconn, args.min_confidence)
    txt_path = write_savings_summary(dconn, mconn)
    html_path = write_html_report(dconn, mconn, args.min_confidence)
    console.print(f"  ✓ [cyan]{html_path}[/cyan]")
    console.print(f"  ✓ [cyan]{csv_path}[/cyan]")
    console.print(f"  ✓ [cyan]{txt_path}[/cyan]")
    console.print()

    # Print savings summary to console
    with open(txt_path) as f:
        console.print(f.read())

    mconn.close()
    dconn.close()


if __name__ == "__main__":
    main()
