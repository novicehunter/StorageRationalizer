#!/usr/bin/env python3
"""
StorageRationalizer — Rollback Tool
Parses cleanup_*.log files, stores deleted-file records in rollback.db,
and restores files from macOS Trash / OneDrive Recycle Bin / Google Drive
Trash / iCloud Photos Recently Deleted.

Usage:
    python3 tools/rollback.py --sync
    python3 tools/rollback.py --restore --run-id 20260308_124626 --scope run
    python3 tools/rollback.py --restore --run-id 20260308_124626 --scope source \
        --source macbook_local
    python3 tools/rollback.py --restore --run-id 20260308_124626 --scope folder \
        --folder "/Users/foo/Downloads"
    python3 tools/rollback.py --restore --file-ids 1,2,3
"""

import argparse
import glob
import json
import logging
import re
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from tools.input_validators import (
    InputValidationError,
    sanitize_applescript_string,
    validate_file_path,
)

logger = logging.getLogger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE = Path(__file__).parent.parent
LOGS_DIR = BASE / "logs"
ROLLBACK_DB = BASE / "manifests" / "rollback.db"
MANIFEST_DB = BASE / "manifests" / "manifest.db"
CREDS_DIR = BASE / "credentials"
REPORTS_DIR = BASE / "reports"


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def fmt_size(b):
    if not b:
        return "0 B"
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"


# ── Database ──────────────────────────────────────────────────────────────────


def get_db():
    ROLLBACK_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ROLLBACK_DB))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS cleanup_runs (
                run_id        TEXT PRIMARY KEY,
                log_file      TEXT NOT NULL,
                timestamp     TEXT,
                mode          TEXT,
                total_deleted INTEGER DEFAULT 0,
                total_files   INTEGER DEFAULT 0,
                total_size    INTEGER DEFAULT 0,
                is_complete   INTEGER DEFAULT 0,
                synced_at     TEXT
            )
        """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS deleted_files (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id        TEXT    NOT NULL,
                file_id       TEXT,
                cloud_id      TEXT,
                source        TEXT    NOT NULL,
                filename      TEXT    NOT NULL,
                source_path   TEXT,
                trash_path    TEXT,
                parent_folder TEXT,
                file_size     INTEGER,
                deleted_at    TEXT    NOT NULL,
                restored      INTEGER DEFAULT 0,
                restored_at   TEXT,
                restore_error TEXT,
                FOREIGN KEY (run_id) REFERENCES cleanup_runs(run_id)
            )
        """
        )
        db.execute("CREATE INDEX IF NOT EXISTS idx_df_run    ON deleted_files(run_id)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_df_source ON deleted_files(source)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_df_folder ON deleted_files(parent_folder)")
        db.execute("CREATE INDEX IF NOT EXISTS idx_df_restored ON deleted_files(restored)")
        db.commit()


# ── Log parsing ───────────────────────────────────────────────────────────────

_TS_RE = re.compile(r"^\[([^\]]+)\]\s+(.*)")
_LOC_RE = re.compile(r"^(?:DELETED|TRASHED) local (.+?)(?:\s+→\s+(.+))?$")
_GD_RE = re.compile(r"^TRASHED google_drive (\S+) (.+)$")
_OD_RE = re.compile(r"^TRASHED onedrive (\S+) (.+)$")
_ICP_RE = re.compile(r"^DELETED icloud_photos (\S+) (.+)$")
_START_RE = re.compile(r"=== Phase 3 Cleaner started — mode=(\S+) files=(\d+)")
_END_RE = re.compile(r"=== Complete — deleted=(\d+)")


def _infer_local_source(path: str) -> str:
    if "CloudDocs" in path or "iCloud" in path:
        return "icloud_drive"
    return "macbook_local"


def _lookup_sizes(paths: list, cloud_ids: list) -> dict:
    """Return {source_path|cloud_id: file_size} from manifest.db (best-effort, batch)."""
    sizes: Dict[str, int] = {}
    if not MANIFEST_DB.exists():
        return sizes
    try:
        conn = sqlite3.connect(str(MANIFEST_DB))
        paths_clean = [p for p in paths if p]
        if paths_clean:
            ph = ",".join("?" * len(paths_clean))
            rows = conn.execute(
                f"SELECT source_path, file_size FROM files WHERE source_path IN ({ph})",
                paths_clean,
            ).fetchall()
            for row in rows:
                if row[0]:
                    sizes[row[0]] = row[1]
        cids_clean = [c for c in cloud_ids if c]
        if cids_clean:
            ph = ",".join("?" * len(cids_clean))
            rows = conn.execute(
                f"SELECT cloud_file_id, file_size FROM files WHERE cloud_file_id IN ({ph})",
                cids_clean,
            ).fetchall()
            for row in rows:
                if row[0]:
                    sizes[row[0]] = row[1]
        conn.close()
    except Exception:
        pass
    return sizes


def parse_log(log_path: str) -> dict:
    """Parse a single cleanup_*.log → dict with run meta + list of record dicts."""
    lf = Path(log_path)
    run_id = lf.stem.replace("cleanup_", "")
    mode = "unknown"
    total_files = 0
    is_complete = False
    start_ts = None
    records: list[dict] = []

    with open(log_path, "r") as f:
        lines = f.readlines()

    for raw in lines:
        m = _TS_RE.match(raw.strip())
        if not m:
            continue
        ts_str, msg = m.group(1), m.group(2)
        try:
            ts = datetime.fromisoformat(ts_str)
        except ValueError:
            ts = None

        sm = _START_RE.search(msg)
        if sm:
            mode = sm.group(1)
            total_files = int(sm.group(2))
            start_ts = ts
            continue

        if _END_RE.search(msg):
            is_complete = True
            continue

        lm = _LOC_RE.match(msg)
        if lm:
            src_path = lm.group(1).strip()
            trash_pth = lm.group(2).strip() if lm.group(2) else None
            records.append(
                {
                    "source": _infer_local_source(src_path),
                    "filename": Path(src_path).name,
                    "source_path": src_path,
                    "trash_path": trash_pth,
                    "cloud_id": None,
                    "parent_folder": str(Path(src_path).parent),
                    "deleted_at": ts_str,
                }
            )
            continue

        gm = _GD_RE.match(msg)
        if gm:
            records.append(
                {
                    "source": "google_drive",
                    "cloud_id": gm.group(1),
                    "filename": gm.group(2).strip(),
                    "source_path": None,
                    "trash_path": None,
                    "parent_folder": None,
                    "deleted_at": ts_str,
                }
            )
            continue

        om = _OD_RE.match(msg)
        if om:
            records.append(
                {
                    "source": "onedrive",
                    "cloud_id": om.group(1),
                    "filename": om.group(2).strip(),
                    "source_path": None,
                    "trash_path": None,
                    "parent_folder": None,
                    "deleted_at": ts_str,
                }
            )
            continue

        im = _ICP_RE.match(msg)
        if im:
            records.append(
                {
                    "source": "icloud_photos",
                    "cloud_id": im.group(1),
                    "filename": im.group(2).strip(),
                    "source_path": None,
                    "trash_path": None,
                    "parent_folder": None,
                    "deleted_at": ts_str,
                }
            )
            continue

    # Enrich with file sizes from manifest.db
    paths = [r["source_path"] for r in records if r.get("source_path")]
    cloud_ids = [r["cloud_id"] for r in records if r.get("cloud_id")]
    sizes = _lookup_sizes(paths, cloud_ids)
    for r in records:
        key = r.get("source_path") or r.get("cloud_id")
        r["file_size"] = sizes.get(key)

    total_size = sum(r["file_size"] or 0 for r in records)

    return {
        "run_id": run_id,
        "log_file": lf.name,
        "timestamp": start_ts.isoformat() if start_ts else None,
        "mode": mode,
        "total_deleted": len(records),
        "total_files": total_files,
        "total_size": total_size,
        "is_complete": is_complete,
        "records": records,
    }


def sync_all_logs(verbose: bool = True) -> int:
    """Re-parse every cleanup_*.log and upsert into rollback.db. Returns count."""
    init_db()
    log_files = sorted(glob.glob(str(LOGS_DIR / "cleanup_*.log")))
    if not log_files:
        return 0

    db = get_db()
    synced = 0

    for lf in log_files:
        run = parse_log(lf)
        db.execute(
            """
            INSERT INTO cleanup_runs
                (run_id, log_file, timestamp, mode,
                 total_deleted, total_files, total_size, is_complete, synced_at)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(run_id) DO UPDATE SET
                total_deleted = excluded.total_deleted,
                total_size    = excluded.total_size,
                is_complete   = excluded.is_complete,
                synced_at     = excluded.synced_at
        """,
            (
                run["run_id"],
                run["log_file"],
                run["timestamp"],
                run["mode"],
                run["total_deleted"],
                run["total_files"],
                run["total_size"],
                int(run["is_complete"]),
                now_iso(),
            ),
        )

        # Preserve already-restored records; drop and re-insert the rest
        db.execute("DELETE FROM deleted_files WHERE run_id=? AND restored=0", (run["run_id"],))

        for rec in run["records"]:
            # Skip if this exact file was already restored in a previous sync
            dup = db.execute(
                """SELECT id FROM deleted_files
                   WHERE run_id=? AND restored=1
                     AND (source_path=? OR (cloud_id IS NOT NULL AND cloud_id=?))""",
                (run["run_id"], rec.get("source_path"), rec.get("cloud_id")),
            ).fetchone()
            if dup:
                continue
            db.execute(
                """
                INSERT INTO deleted_files
                    (run_id, cloud_id, source, filename, source_path,
                     trash_path, parent_folder, file_size, deleted_at)
                VALUES (?,?,?,?,?,?,?,?,?)
            """,
                (
                    run["run_id"],
                    rec.get("cloud_id"),
                    rec["source"],
                    rec["filename"],
                    rec.get("source_path"),
                    rec.get("trash_path"),
                    rec.get("parent_folder"),
                    rec.get("file_size"),
                    rec["deleted_at"],
                ),
            )

        db.commit()
        synced += 1
        if verbose:
            print(f"  Synced {run['log_file']} — {run['total_deleted']} records")

    db.close()
    return synced


# ── Restore methods ───────────────────────────────────────────────────────────


def _restore_local(rec: dict) -> tuple:
    src = rec.get("source_path")
    trash = rec.get("trash_path")
    name = rec["filename"]

    if not src:
        return False, "No source_path recorded"

    dest = Path(src)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # 1. Known trash_path (TRASHED fallback branch)
    if trash and Path(trash).exists():
        try:
            try:
                safe_trash = validate_file_path(str(trash))
            except InputValidationError as e:
                return False, f"Invalid trash path: {e}"
            shutil.move(safe_trash, str(dest))
            return True, f"Moved {trash} → {src}"
        except Exception as e:
            return False, str(e)

    # 2. Search ~/.Trash by filename
    trash_candidate = Path.home() / ".Trash" / name
    if trash_candidate.exists():
        try:
            try:
                safe_candidate = validate_file_path(str(trash_candidate))
            except InputValidationError as e:
                return False, f"Invalid trash candidate path: {e}"
            shutil.move(safe_candidate, str(dest))
            return True, f"Restored from ~/.Trash/{name}"
        except Exception as e:
            return False, str(e)

    # 3. AppleScript — search Finder Trash by name
    safe_name = sanitize_applescript_string(name)
    safe_dest_parent = sanitize_applescript_string(str(dest.parent))
    script = f"""
tell application "Finder"
    set trashItems to items of trash
    repeat with theItem in trashItems
        if name of theItem is "{safe_name}" then
            move theItem to POSIX file "{safe_dest_parent}"
            return "ok"
        end if
    end repeat
    return "not_found"
end tell
"""
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and "ok" in r.stdout:
            return True, "Restored via Finder Trash"
        return False, f"Not found in macOS Trash (filename: {name})"
    except Exception as e:
        return False, str(e)


def _restore_google_drive(rec: dict) -> tuple:
    cid = rec.get("cloud_id")
    if not cid:
        return False, "No cloud_id"
    token_file = CREDS_DIR / "google_token.json"
    if not token_file.exists():
        return False, "google_token.json not found — authenticate via cleaner.py first"
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        with open(token_file) as f:
            td = json.load(f)
        creds = Credentials(
            token=td.get("token"),
            refresh_token=td.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=td.get("client_id"),
            client_secret=td.get("client_secret"),
        )
        svc = build("drive", "v3", credentials=creds)
        svc.files().update(
            fileId=cid,
            body={"trashed": False},
            supportsAllDrives=True,
        ).execute()
        return True, f"Untrashed GDrive file {cid}"
    except Exception as e:
        return False, str(e)


def _restore_onedrive(rec: dict) -> tuple:
    cid = rec.get("cloud_id")
    if not cid:
        return False, "No cloud_id"
    token_file = CREDS_DIR / "onedrive_token.json"
    if not token_file.exists():
        return False, "onedrive_token.json not found — authenticate via cleaner.py first"
    try:
        import requests
        from tools.api_validators import APIResponseError, validate_restore_response

        with open(token_file) as f:
            td = json.load(f)
        token = td.get("access_token")
        if not token:
            return False, "OneDrive access_token missing or expired"

        resp = requests.post(
            f"https://graph.microsoft.com/v1.0/me/drive/items/{cid}/restore",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={},
            timeout=30,
        )

        # Validate response body — not just HTTP status code
        try:
            validated = validate_restore_response(resp, expected_file_id=cid)
            logger.info("OneDrive restore validated: %s (%s)", cid, validated.get("name", cid))
            return True, f"Restored OneDrive item {cid}"
        except APIResponseError as e:
            logger.error("Restore validation failed for %s: %s", cid, e.message)
            return False, f"Restore failed: {e.message}"

    except requests.Timeout:
        logger.error("Restore request timed out for %s", cid)
        return False, "Timeout"
    except (APIResponseError,) as e:
        logger.error("Restore validation failed for %s: %s", cid, e.message)
        return False, f"Restore failed: {e.message}"
    except Exception as e:
        return False, str(e)


def _restore_icloud_photos(rec: dict) -> tuple:
    cid = rec.get("cloud_id")
    name = rec["filename"]
    if not cid:
        return False, "No cloud_id"
    safe_cid = sanitize_applescript_string(cid)
    script = f"""
tell application "Photos"
    set deletedAlbum to recently deleted album
    set thePhotos to media items of deletedAlbum
    repeat with thePhoto in thePhotos
        if id of thePhoto is "{safe_cid}" then
            recover thePhoto
            return "ok"
        end if
    end repeat
    return "not_found"
end tell
"""
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and "ok" in r.stdout:
            return True, f"Recovered iCloud Photos item {cid}"
        return False, f"Not found in Recently Deleted (id: {cid}, file: {name})"
    except Exception as e:
        return False, str(e)


def _restore_one(rec: dict) -> tuple:
    src = rec["source"]
    if src in ("macbook_local", "icloud_drive", "local"):
        return _restore_local(rec)
    if src == "google_drive":
        return _restore_google_drive(rec)
    if src == "onedrive":
        return _restore_onedrive(rec)
    if src == "icloud_photos":
        return _restore_icloud_photos(rec)
    return False, f"Unknown source: {src}"


def restore_files(file_ids: list) -> list:
    """Restore deleted_files rows by id. Updates DB. Returns list of result dicts."""
    db = get_db()
    results = []
    for fid in file_ids:
        row = db.execute("SELECT * FROM deleted_files WHERE id=?", (fid,)).fetchone()
        if not row:
            results.append({"id": fid, "ok": False, "msg": "Record not found"})
            continue
        if row["restored"]:
            results.append(
                {
                    "id": fid,
                    "filename": row["filename"],
                    "source": row["source"],
                    "ok": True,
                    "msg": "Already restored",
                }
            )
            continue
        rec = dict(row)
        ok, msg = _restore_one(rec)
        ts = now_iso()
        if ok:
            db.execute(
                "UPDATE deleted_files SET restored=1, restored_at=?, restore_error=NULL WHERE id=?",
                (ts, fid),
            )
        else:
            db.execute("UPDATE deleted_files SET restore_error=? WHERE id=?", (msg, fid))
        db.commit()
        results.append(
            {"id": fid, "filename": rec["filename"], "source": rec["source"], "ok": ok, "msg": msg}
        )
    db.close()
    return results


def build_restore_ids(
    run_id: str, scope: str, source: Optional[str] = None, folder: Optional[str] = None
) -> list:
    """Return list of deleted_files.id matching the given scope."""
    db = get_db()
    if scope == "run":
        rows = db.execute(
            "SELECT id FROM deleted_files WHERE run_id=? AND restored=0", (run_id,)
        ).fetchall()
    elif scope == "source" and source:
        rows = db.execute(
            "SELECT id FROM deleted_files WHERE run_id=? AND source=? AND restored=0",
            (run_id, source),
        ).fetchall()
    elif scope == "folder" and folder:
        rows = db.execute(
            "SELECT id FROM deleted_files WHERE run_id=? AND parent_folder=? AND restored=0",
            (run_id, folder),
        ).fetchall()
    else:
        rows = []
    db.close()
    return [r["id"] for r in rows]


# ── HTML Report ───────────────────────────────────────────────────────────────


def generate_report(run_id: str, results: list) -> str:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = REPORTS_DIR / f"rollback_report_{ts}.html"

    ok_n = sum(1 for r in results if r.get("ok"))
    fail_n = len(results) - ok_n

    rows_html = "".join(
        f"""<tr>
  <td style="color:{'#3ecf8e' if r.get('ok') else '#e05c65'};text-align:center;font-size:16px">
    {'&#10003;' if r.get('ok') else '&#10007;'}
  </td>
  <td style="font-family:monospace;color:#8892a4">{r.get('source', '')}</td>
  <td>{r.get('filename', '')}</td>
  <td style="color:{'#3ecf8e' if r.get('ok') else '#e05c65'};font-size:12px">{r.get('msg', '')}</td>
</tr>"""
        for r in results
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Rollback Report — {ts}</title>
<style>
  body {{ background:#0f1117; color:#e2e8f0;
          font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
          padding:32px; font-size:14px; line-height:1.6; }}
  h1   {{ color:#5b8dee; font-size:22px; margin-bottom:4px; }}
  h2   {{ color:#8892a4; font-size:13px; font-weight:400; margin-bottom:24px; }}
  .summary {{ display:flex; gap:16px; margin-bottom:28px; flex-wrap:wrap; }}
  .stat {{ background:#1a1d27; border:1px solid #2a2d3a; border-radius:10px;
           padding:14px 22px; min-width:120px; }}
  .sv  {{ font-size:28px; font-weight:700; margin-bottom:2px; }}
  .sl  {{ font-size:12px; color:#8892a4; text-transform:uppercase; letter-spacing:.4px; }}
  table {{ width:100%; border-collapse:collapse; }}
  thead tr {{ background:#2a2d3a; }}
  th   {{ padding:10px 14px; text-align:left; font-size:11px; color:#8892a4;
           text-transform:uppercase; letter-spacing:.4px; }}
  td   {{ padding:9px 14px; border-bottom:1px solid #1f2230; vertical-align:middle; }}
  tr:last-child td {{ border-bottom:none; }}
</style>
</head>
<body>
<h1>StorageRationalizer — Rollback Report</h1>
<h2>Run ID: {run_id} &nbsp;·&nbsp; Generated: {ts.replace('_', ' ')}</h2>
<div class="summary">
  <div class="stat"><div class="sv" style="color:#3ecf8e">{ok_n}</div>
    <div class="sl">Restored</div></div>
  <div class="stat"><div class="sv" style="color:#e05c65">{fail_n}</div>
    <div class="sl">Failed</div></div>
  <div class="stat"><div class="sv">{len(results)}</div>
    <div class="sl">Total</div></div>
</div>
<table>
  <thead>
    <tr><th></th><th>Source</th><th>Filename</th><th>Result</th></tr>
  </thead>
  <tbody>{rows_html}</tbody>
</table>
</body>
</html>"""

    with open(fname, "w") as f:
        f.write(html)
    return str(fname)


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="StorageRationalizer — Rollback Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--sync", action="store_true", help="Re-parse all cleanup_*.log files into rollback.db"
    )
    parser.add_argument(
        "--restore", action="store_true", help="Restore files from trash/recycle-bin"
    )
    parser.add_argument("--run-id", help="Cleanup run ID (e.g. 20260308_124626)")
    parser.add_argument(
        "--scope", choices=["run", "source", "folder", "files"], help="Restore scope"
    )
    parser.add_argument("--source", help="Source filter (scope=source)")
    parser.add_argument("--folder", help="Parent folder filter (scope=folder)")
    parser.add_argument("--file-ids", help="Comma-separated deleted_files.id list (scope=files)")
    args = parser.parse_args()

    if args.sync:
        print("Syncing cleanup logs → rollback.db …")
        n = sync_all_logs(verbose=True)
        print(f"Done — {n} log(s) synced.")

    elif args.restore:
        init_db()
        if args.file_ids:
            ids = [int(x.strip()) for x in args.file_ids.split(",") if x.strip()]
        elif args.run_id and args.scope:
            ids = build_restore_ids(
                args.run_id,
                args.scope,
                source=args.source,
                folder=args.folder,
            )
        else:
            parser.error("Provide --run-id + --scope, or --file-ids")

        if not ids:
            print("No matching files to restore.")
        else:
            print(f"Restoring {len(ids)} file(s) …")
            results = restore_files(ids)
            ok_n = sum(1 for r in results if r["ok"])
            print(f"Done — {ok_n}/{len(results)} restored.")
            report = generate_report(args.run_id or "manual", results)
            print(f"Report: {report}")
    else:
        parser.print_help()
