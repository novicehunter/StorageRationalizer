#!/usr/bin/env python3
"""
StorageRationalizer — Phase 3 Cleaner
Deletes confirmed duplicate files. Always dry-run first.

Modes:
  --mode safe   100% confidence only — all file types (96 files, ~709MB)
  --mode docs   90%+ docs/archives only — no photos/videos (26,833 files, ~140.7GB)
  --mode all    Both combined — full safe cleanup (~141.4GB)

ALWAYS run with --dry-run first to review what will be deleted.
Nothing is permanently deleted — everything goes to recoverable bins:
  Local files  → macOS Trash (recover from Finder)
  OneDrive     → OneDrive Recycle Bin (recover within 30 days)
  Google Drive → Google Trash (recover within 30 days)
  iCloud Photos→ Recently Deleted album (recover within 30 days)

Usage:
    python3 cleaner.py --dry-run --mode all       # ALWAYS start here
    python3 cleaner.py --mode safe                # 100% confirmed, all types
    python3 cleaner.py --mode docs                # 90%+ docs/archives only
    python3 cleaner.py --mode all                 # full safe cleanup
    python3 cleaner.py --mode all --source onedrive  # one source at a time
"""

import sqlite3, json, argparse, os, shutil, time
from pathlib import Path
from datetime import datetime, timezone

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.prompt import Confirm

console = Console()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE        = Path.home() / "Desktop" / "StorageRationalizer"
CREDS_DIR   = BASE / "credentials"
MANIFEST_DB = BASE / "manifests" / "manifest.db"
DUPES_DB    = BASE / "manifests" / "duplicates.db"
LOGS_DIR    = BASE / "logs"

PHOTO_EXTS = {'.jpg','.jpeg','.png','.heic','.heif','.gif','.tiff','.bmp','.webp','.raw','.cr2','.dng'}
VIDEO_EXTS = {'.mp4','.mov','.avi','.mkv','.m4v','.wmv','.3gp','.mts','.m2ts'}
MEDIA_EXTS = PHOTO_EXTS | VIDEO_EXTS


# ── Helpers ────────────────────────────────────────────────────────────────────
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def format_size(b):
    if not b: return '0 B'
    b = int(b)
    for u in ['B','KB','MB','GB','TB']:
        if b < 1024: return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"

def get_log_path():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    return LOGS_DIR / f"cleanup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

def log(log_file, msg):
    with open(log_file, 'a') as f:
        f.write(f"[{now_iso()}] {msg}\n")


# ── Mode Filters ───────────────────────────────────────────────────────────────
def build_query(mode: str, source_filter: str) -> tuple:
    """
    Returns (WHERE clause, params) for selecting files to delete.
    safe: 100% confidence, all file types
    docs: 90%+ confidence, no media
    all:  100% all types + 90%+ docs
    """
    source_clause = f"AND m.source = ?" if source_filter else ""
    params = []
    if source_filter:
        params.append(source_filter)

    if mode == 'safe':
        where = f"""
            m.action = 'delete'
            AND g.confidence = 100
            {source_clause}
        """
    elif mode == 'docs':
        media_list = "'" + "','".join([e.lstrip('.') for e in MEDIA_EXTS]) + "'"
        where = f"""
            m.action = 'delete'
            AND g.confidence >= 90
            AND LOWER(SUBSTR(m.filename, INSTR(m.filename, '.') + 1)) NOT IN ({media_list})
            {source_clause}
        """
    elif mode == 'all':
        media_list = "'" + "','".join([e.lstrip('.') for e in MEDIA_EXTS]) + "'"
        where = f"""
            m.action = 'delete'
            AND (
                g.confidence = 100
                OR (
                    g.confidence >= 90
                    AND LOWER(SUBSTR(m.filename, INSTR(m.filename, '.') + 1)) NOT IN ({media_list})
                )
            )
            {source_clause}
        """
    else:
        raise ValueError(f"Unknown mode: {mode}")

    return where, params


# ── Cloud Auth ─────────────────────────────────────────────────────────────────
def get_google_creds():
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        token_file = CREDS_DIR / 'google_token.json'
        if not token_file.exists():
            return None
        creds = Credentials.from_authorized_user_file(str(token_file))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, 'w') as f:
                f.write(creds.to_json())
        return creds
    except Exception as e:
        console.print(f"[red]Google auth error: {e}[/red]")
        return None

def get_onedrive_token():
    try:
        import msal
        creds_file = CREDS_DIR / 'onedrive_credentials.txt'
        token_file = CREDS_DIR / 'onedrive_token.json'
        if not creds_file.exists():
            return None
        creds = {}
        with open(creds_file) as f:
            for line in f:
                if '=' in line:
                    k, v = line.strip().split('=', 1)
                    creds[k.strip()] = v.strip()

        if token_file.exists():
            with open(token_file) as f:
                cached = json.load(f)
                if cached.get('expires_at', 0) > datetime.now().timestamp() + 60:
                    return cached.get('access_token')

        app = msal.PublicClientApplication(
            creds['CLIENT_ID'],
            authority="https://login.microsoftonline.com/consumers"
        )
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(['Files.ReadWrite.All'], account=accounts[0])
            if result and 'access_token' in result:
                return result['access_token']

        flow = app.initiate_device_flow(scopes=['Files.ReadWrite.All'])
        console.print(f"[yellow]{flow['message']}[/yellow]")
        result = app.acquire_token_by_device_flow(flow)
        if 'access_token' in result:
            token = result['access_token']
            with open(token_file, 'w') as f:
                json.dump({'access_token': token,
                           'expires_at': datetime.now().timestamp() + result.get('expires_in', 3600)}, f)
            return token
    except Exception as e:
        console.print(f"[red]OneDrive auth error: {e}[/red]")
    return None


# ── Delete Methods ─────────────────────────────────────────────────────────────

def delete_local(path: str, dry_run: bool, log_file) -> bool:
    """Move local file to macOS Trash."""
    p = Path(path)
    if not p.exists():
        log(log_file, f"SKIP_NOT_FOUND local {path}")
        return False
    if dry_run:
        log(log_file, f"DRY_RUN local {path}")
        return True
    try:
        # Use AppleScript to move to Trash — preserves recovery
        import subprocess
        result = subprocess.run(
            ['osascript', '-e',
             f'tell application "Finder" to delete POSIX file "{path}"'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            log(log_file, f"DELETED local {path}")
            return True
        else:
            # Fallback: move to ~/.Trash manually
            trash = Path.home() / '.Trash' / p.name
            counter = 1
            while trash.exists():
                trash = Path.home() / '.Trash' / f"{p.stem}_{counter}{p.suffix}"
                counter += 1
            shutil.move(str(p), str(trash))
            log(log_file, f"TRASHED local {path} → {trash}")
            return True
    except Exception as e:
        log(log_file, f"ERROR local {path}: {e}")
        return False


def delete_google_drive(file_id: str, filename: str, dry_run: bool,
                        creds, log_file) -> bool:
    """Move Google Drive file to Trash (recoverable within 30 days)."""
    if dry_run:
        log(log_file, f"DRY_RUN google_drive {file_id} {filename}")
        return True
    try:
        from googleapiclient.discovery import build
        service = build('drive', 'v3', credentials=creds)
        service.files().update(
            fileId=file_id,
            body={'trashed': True},
            supportsAllDrives=True
        ).execute()
        log(log_file, f"TRASHED google_drive {file_id} {filename}")
        return True
    except Exception as e:
        log(log_file, f"ERROR google_drive {file_id} {filename}: {e}")
        return False


ONEDRIVE_BATCH_SIZE = 20  # Graph API $batch max


def batch_delete_onedrive(items: list, token: str, log_file) -> dict:
    """
    Delete up to 20 OneDrive items in a single Graph API $batch call.
    items: list of (row_id, file_id, cloud_id, filename)
    Returns dict of cloud_id -> bool
    """
    import requests
    batch_requests = [
        {"id": str(i), "method": "DELETE", "url": f"/me/drive/items/{cloud_id}"}
        for i, (_, _, cloud_id, _) in enumerate(items)
    ]
    try:
        resp = requests.post(
            'https://graph.microsoft.com/v1.0/$batch',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            json={"requests": batch_requests},
            timeout=60
        )
        resp.raise_for_status()
        responses = resp.json().get('responses', [])
    except Exception as e:
        log(log_file, f"BATCH_ERROR onedrive: {e}")
        return {cloud_id: False for _, _, cloud_id, _ in items}

    results = {}
    for r in responses:
        idx    = int(r['id'])
        _, _, cloud_id, filename = items[idx]
        status = r.get('status', 0)
        if status in (200, 204):
            log(log_file, f"TRASHED onedrive {cloud_id} {filename}")
            results[cloud_id] = True
        else:
            log(log_file, f"ERROR onedrive {cloud_id} {filename}: HTTP {status}")
            results[cloud_id] = False
    return results


def delete_icloud_photos(file_id: str, filename: str, dry_run: bool, log_file) -> bool:
    """Delete from iCloud Photos via osxphotos — goes to Recently Deleted."""
    if dry_run:
        log(log_file, f"DRY_RUN icloud_photos {file_id} {filename}")
        return True
    try:
        import osxphotos
        photos_lib = Path.home() / "Pictures" / "Photos Library.photoslibrary"
        db = osxphotos.PhotosDB(str(photos_lib))
        photos = db.photos(uuid=[file_id])
        if not photos:
            log(log_file, f"NOT_FOUND icloud_photos {file_id} {filename}")
            return False
        # osxphotos delete requires Photos app — use applescript
        import subprocess
        script = f'''
        tell application "Photos"
            set thePhoto to media item id "{file_id}"
            delete thePhoto
        end tell
        '''
        result = subprocess.run(['osascript', '-e', script],
                                capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            log(log_file, f"DELETED icloud_photos {file_id} {filename}")
            return True
        else:
            log(log_file, f"ERROR icloud_photos {file_id}: {result.stderr}")
            return False
    except Exception as e:
        log(log_file, f"ERROR icloud_photos {file_id} {filename}: {e}")
        return False


# ── Dry Run Preview ────────────────────────────────────────────────────────────
def print_dry_run_preview(rows, mode):
    by_source = {}
    for r in rows:
        src = r['source']
        if src not in by_source:
            by_source[src] = {'count': 0, 'size': 0, 'samples': []}
        by_source[src]['count'] += 1
        by_source[src]['size']  += r['file_size'] or 0
        if len(by_source[src]['samples']) < 3:
            by_source[src]['samples'].append(r)

    console.print()
    console.rule(f"[bold yellow]DRY RUN — Mode: {mode.upper()}[/bold yellow]")
    console.print()

    table = Table(show_header=True, header_style="bold navy_blue")
    table.add_column("Source",   style="cyan",  min_width=18)
    table.add_column("Files",    style="white", justify="right")
    table.add_column("Size",     style="green", justify="right")
    table.add_column("Sample files", style="dim")

    total_files = 0
    total_size  = 0
    for src, d in sorted(by_source.items(), key=lambda x: -x[1]['size']):
        samples = ' | '.join(s['filename'][:30] for s in d['samples'])
        table.add_row(src, str(d['count']), format_size(d['size']), samples)
        total_files += d['count']
        total_size  += d['size']

    console.print(table)
    console.print()
    console.print(f"  [bold]Total files to delete:[/bold] {total_files:,}")
    console.print(f"  [bold]Total space to recover:[/bold] [green]{format_size(total_size)}[/green]")
    console.print()
    console.print("  [dim]All deletions go to recoverable bins (Trash / Recycle Bin).[/dim]")
    console.print("  [dim]Run without --dry-run to execute.[/dim]")
    console.print()


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description='StorageRationalizer Phase 3 Cleaner')
    parser.add_argument('--mode',     choices=['safe','docs','all'], default='safe',
                        help='safe=100%% only | docs=90%%+ no media | all=both')
    parser.add_argument('--dry-run',  action='store_true',
                        help='Preview what would be deleted without touching anything')
    parser.add_argument('--source',   help='Limit to one source (e.g. onedrive)')
    parser.add_argument('--limit',    type=int, default=0,
                        help='Limit number of files (for testing)')
    args = parser.parse_args()

    console.rule("[bold red]StorageRationalizer — Phase 3 Cleaner[/bold red]")
    console.print(f"  Mode:     [cyan]{args.mode}[/cyan]")
    console.print(f"  Dry run:  [cyan]{'YES — nothing will be deleted' if args.dry_run else 'NO — files will be deleted'}[/cyan]")
    if args.source:
        console.print(f"  Source:   [cyan]{args.source}[/cyan]")
    console.print()

    if not MANIFEST_DB.exists():
        console.print("[red]Manifest DB not found. Run Phase 1 scanner first.[/red]")
        return
    if not DUPES_DB.exists():
        console.print("[red]Duplicates DB not found. Run Phase 2 classifier first.[/red]")
        return

    mconn = sqlite3.connect(str(MANIFEST_DB))
    mconn.row_factory = sqlite3.Row
    dconn = sqlite3.connect(str(DUPES_DB))
    dconn.row_factory = sqlite3.Row

    # Build query
    where, params = build_query(args.mode, args.source)
    limit_clause  = f"LIMIT {args.limit}" if args.limit else ""

    query = f"""
        SELECT m.id, m.group_id, m.file_id, m.source, m.filename,
               m.file_size, m.source_path, m.cloud_file_id,
               m.action, m.confidence, g.match_type
        FROM duplicate_members m
        JOIN duplicate_groups g ON m.group_id = g.group_id
        WHERE {where}
        ORDER BY m.source, g.wasted_size DESC
        {limit_clause}
    """

    rows = dconn.execute(query, params).fetchall()

    if not rows:
        console.print("[yellow]No files found matching this mode/filter.[/yellow]")
        return

    # Always show dry run preview first
    print_dry_run_preview(rows, args.mode)

    if args.dry_run:
        return

    # Confirm before proceeding
    if not Confirm.ask(f"[bold red]Delete {len(rows):,} files? This sends them to recoverable bins.[/bold red]"):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Auth for cloud sources
    sources_needed = set(r['source'] for r in rows)
    gcreds   = None
    od_token = None

    if 'google_drive' in sources_needed:
        console.print("[dim]Connecting to Google Drive...[/dim]")
        gcreds = get_google_creds()
        if gcreds:
            console.print("  [green]✓ Google Drive[/green]")
        else:
            console.print("  [yellow]⚠ Google Drive unavailable — will skip[/yellow]")

    if 'onedrive' in sources_needed:
        console.print("[dim]Connecting to OneDrive...[/dim]")
        od_token = get_onedrive_token()
        if od_token:
            console.print("  [green]✓ OneDrive[/green]")
        else:
            console.print("  [yellow]⚠ OneDrive unavailable — will skip[/yellow]")

    console.print()

    log_file = get_log_path()
    log(log_file, f"=== Phase 3 Cleaner started — mode={args.mode} files={len(rows)} ===")

    stats = {'deleted': 0, 'skipped': 0, 'errors': 0}

    # Split rows: OneDrive uses batch API, everything else is single-item
    onedrive_rows = [r for r in rows if r['source'] == 'onedrive']
    other_rows    = [r for r in rows if r['source'] != 'onedrive']

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  BarColumn(), TextColumn("{task.completed}/{task.total}"),
                  TimeElapsedColumn(), console=console) as progress:

        task = progress.add_task("Deleting...", total=len(rows))
        completed = 0

        # ── Non-OneDrive sources (single-item) ───────────────────────────────
        for i, row in enumerate(other_rows):
            source     = row['source']
            filename   = row['filename']
            cloud_id   = row['cloud_file_id']
            local_path = row['source_path']
            file_id    = row['file_id']

            progress.update(task,
                description=f"[red]Deleting[/red] [{source}] {filename[:50]}",
                completed=completed)

            ok = False

            if source in ('macbook_local', 'icloud_drive'):
                if local_path:
                    ok = delete_local(local_path, False, log_file)
                else:
                    log(log_file, f"SKIP_NO_PATH {source} {filename}")

            elif source == 'google_drive':
                if gcreds and cloud_id:
                    ok = delete_google_drive(cloud_id, filename, False, gcreds, log_file)
                    time.sleep(0.1)  # Google Drive API rate limit
                else:
                    log(log_file, f"SKIP_NO_AUTH google_drive {filename}")

            elif source == 'icloud_photos':
                if cloud_id:
                    ok = delete_icloud_photos(cloud_id, filename, False, log_file)
                else:
                    log(log_file, f"SKIP_NO_ID icloud_photos {filename}")

            if ok:
                stats['deleted'] += 1
                dconn.execute("UPDATE duplicate_members SET action='deleted' WHERE id=?", (row['id'],))
                mconn.execute("UPDATE files SET scan_error='DELETED_PHASE3' WHERE file_id=?", (file_id,))
            else:
                stats['skipped'] += 1

            completed += 1
            if completed % 20 == 0:
                dconn.commit()
                mconn.commit()

        # ── OneDrive: batched deletes (20 per Graph API $batch call) ─────────
        for batch_start in range(0, len(onedrive_rows), ONEDRIVE_BATCH_SIZE):
            batch = onedrive_rows[batch_start:batch_start + ONEDRIVE_BATCH_SIZE]

            progress.update(task,
                description=f"[red]Deleting[/red] [onedrive] batch {batch_start // ONEDRIVE_BATCH_SIZE + 1} "
                            f"({batch_start}–{batch_start + len(batch)})",
                completed=completed)

            if not od_token:
                for row in batch:
                    log(log_file, f"SKIP_NO_AUTH onedrive {row['filename']}")
                    stats['skipped'] += 1
                completed += len(batch)
                continue

            items = [
                (row['id'], row['file_id'], row['cloud_file_id'], row['filename'])
                for row in batch if row['cloud_file_id']
            ]
            no_id = [row for row in batch if not row['cloud_file_id']]
            for row in no_id:
                log(log_file, f"SKIP_NO_ID onedrive {row['filename']}")
                stats['skipped'] += 1

            if items:
                results = batch_delete_onedrive(items, od_token, log_file)
                for row_id, file_id, cloud_id, _ in items:
                    if results.get(cloud_id):
                        stats['deleted'] += 1
                        dconn.execute("UPDATE duplicate_members SET action='deleted' WHERE id=?", (row_id,))
                        mconn.execute("UPDATE files SET scan_error='DELETED_PHASE3' WHERE file_id=?", (file_id,))
                    else:
                        stats['skipped'] += 1

            dconn.commit()
            mconn.commit()
            completed += len(batch)

        progress.update(task, completed=len(rows))

    dconn.commit()
    mconn.commit()

    log(log_file, f"=== Complete — deleted={stats['deleted']} skipped={stats['skipped']} errors={stats['errors']} ===")

    # Final summary
    console.print()
    console.rule("[bold green]Phase 3 Complete[/bold green]")
    console.print()

    table = Table(show_header=True, header_style="bold navy_blue")
    table.add_column("Result",  style="cyan")
    table.add_column("Count",   style="white", justify="right")

    table.add_row("✓ Deleted (sent to bin)", str(stats['deleted']))
    table.add_row("~ Skipped (no access)",   str(stats['skipped']))
    table.add_row("✗ Errors",                str(stats['errors']))

    console.print(table)
    console.print()
    console.print(f"  [bold]Audit log:[/bold] [cyan]{log_file}[/cyan]")
    console.print()
    console.print("  [dim]Next steps:[/dim]")
    console.print("  [dim]1. Check bins (Trash / OneDrive Recycle Bin / Google Trash) before emptying[/dim]")
    console.print("  [dim]2. Re-run Phase 1 scanner to update manifest[/dim]")
    console.print("  [dim]3. Re-run Phase 2 classifier for next round[/dim]")
    console.print()
    console.rule()

    mconn.close()
    dconn.close()


if __name__ == '__main__':
    main()
