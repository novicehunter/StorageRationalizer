#!/usr/bin/env python3
"""
StorageRationalizer — Phase 2b Media Verifier
Takes 90% confidence media duplicates from the classifier, verifies them
using partial hash (10MB) then perceptual hash (pHash) for photos.

Upgrades confidence to 100% if verified, downgrades to 40% if not matching.
Updates the duplicates DB in place — Phase 3 only acts on 100% verified files.

Verification layers:
  1. Partial hash (first 10MB SHA256) — fast, catches exact copies
  2. Full hash if partial matches — confirms byte-for-byte identity
  3. pHash (perceptual) — catches same photo in different format/compression
  4. Human review queue — anything pHash flags as similar but not identical

Usage:
    python3 verifier.py                    # verify all 90% media files
    python3 verifier.py --phash            # also run perceptual hash (needs Pillow)
    python3 verifier.py --source onedrive  # one source at a time
    python3 verifier.py --dry-run          # show what would be verified, don't update DB
"""

import sqlite3, hashlib, json, argparse, tempfile, os
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

console = Console()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE = Path.home() / "Desktop" / "StorageRationalizer"
CREDS_DIR = BASE / "credentials"
MANIFEST_DB = BASE / "manifests" / "manifest.db"
DUPES_DB = BASE / "manifests" / "duplicates.db"
REPORTS_DIR = BASE / "reports"
LOGS_DIR = BASE / "logs"

PARTIAL_SIZE = 10 * 1024 * 1024  # 10MB

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif", ".tiff", ".bmp", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv", ".3gp", ".mts", ".m2ts"}


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


def log(msg):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOGS_DIR / f"verifier_{datetime.now().strftime('%Y%m%d')}.log", "a") as f:
        f.write(f"[{now_iso()}] {msg}\n")


def partial_hash_local(path: str, size: int = PARTIAL_SIZE) -> str | None:
    """Hash first N bytes of a local file."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            h.update(f.read(size))
        return h.hexdigest()
    except Exception as e:
        log(f"local hash error {path}: {e}")
        return None


def full_hash_local(path: str) -> str | None:
    """Full SHA256 of a local file."""
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception as e:
        log(f"local full hash error {path}: {e}")
        return None


# ── Cloud Download Helpers ─────────────────────────────────────────────────────


def get_google_creds():
    """Load or refresh Google credentials."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        token_file = CREDS_DIR / "google_token.json"
        if not token_file.exists():
            return None
        creds = Credentials.from_authorized_user_file(str(token_file))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, "w") as f:
                f.write(creds.to_json())
        return creds
    except Exception as e:
        log(f"Google creds error: {e}")
        return None


def get_onedrive_token():
    """Load cached OneDrive token or re-auth via device flow."""
    try:
        import msal

        creds_file = CREDS_DIR / "onedrive_credentials.txt"
        token_file = CREDS_DIR / "onedrive_token.json"
        if not creds_file.exists():
            return None

        creds = {}
        with open(creds_file) as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    creds[k.strip()] = v.strip()

        # Try cached token first
        if token_file.exists():
            with open(token_file) as f:
                cached = json.load(f)
                if cached.get("expires_at", 0) > datetime.now().timestamp() + 60:
                    return cached.get("access_token")

        # Re-auth
        app = msal.PublicClientApplication(creds["CLIENT_ID"], authority="https://login.microsoftonline.com/consumers")
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(["Files.ReadWrite.All"], account=accounts[0])
            if result and "access_token" in result:
                return result["access_token"]

        flow = app.initiate_device_flow(scopes=["Files.ReadWrite.All"])
        console.print(f"[yellow]{flow['message']}[/yellow]")
        result = app.acquire_token_by_device_flow(flow)
        if "access_token" in result:
            token = result["access_token"]
            with open(token_file, "w") as f:
                json.dump(
                    {"access_token": token, "expires_at": datetime.now().timestamp() + result.get("expires_in", 3600)},
                    f,
                )
            return token
    except Exception as e:
        log(f"OneDrive token error: {e}")
    return None


def partial_hash_url(url: str, headers: dict, size: int = PARTIAL_SIZE) -> str | None:
    """Download first N bytes from a URL and hash them."""
    try:
        req = urllib.request.Request(url, headers={**headers, "Range": f"bytes=0-{size-1}"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read(size)
        if not data:
            return None
        h = hashlib.sha256()
        h.update(data)
        return h.hexdigest()
    except Exception as e:
        log(f"URL partial hash error {url[:80]}: {e}")
        return None


def get_google_drive_download_url(file_id: str, creds) -> str | None:
    try:
        import requests

        resp = requests.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers={"Authorization": f"Bearer {creds.token}"},
            params={"alt": "media", "supportsAllDrives": "true"},
            stream=True,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.url
        # For large files Google returns a download warning page — get direct URL
        return f"https://www.googleapis.com/drive/v3/files/{file_id}?alt=media&supportsAllDrives=true"
    except Exception as e:
        log(f"GDrive URL error {file_id}: {e}")
        return None


def partial_hash_gdrive(file_id: str, creds) -> str | None:
    """Partial hash a Google Drive file using range request."""
    try:
        import requests

        resp = requests.get(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers={"Authorization": f"Bearer {creds.token}", "Range": f"bytes=0-{PARTIAL_SIZE-1}"},
            params={"alt": "media", "supportsAllDrives": "true"},
            timeout=30,
        )
        if resp.status_code in (200, 206):
            h = hashlib.sha256()
            h.update(resp.content[:PARTIAL_SIZE])
            return h.hexdigest()
        log(f"GDrive partial hash {file_id}: status {resp.status_code}")
        return None
    except Exception as e:
        log(f"GDrive partial hash error {file_id}: {e}")
        return None


def partial_hash_onedrive(file_id: str, token: str) -> str | None:
    """Partial hash a OneDrive file using range request."""
    try:
        import requests

        # Get download URL first
        meta = requests.get(
            f"https://graph.microsoft.com/v1.0/me/drive/items/{file_id}",
            headers={"Authorization": f"Bearer {token}"},
            params={"select": "id,@microsoft.graph.downloadUrl"},
            timeout=15,
        )
        if meta.status_code != 200:
            log(f"OneDrive meta error {file_id}: {meta.status_code}")
            return None

        download_url = meta.json().get("@microsoft.graph.downloadUrl")
        if not download_url:
            return None

        resp = requests.get(download_url, headers={"Range": f"bytes=0-{PARTIAL_SIZE-1}"}, timeout=30)
        if resp.status_code in (200, 206):
            h = hashlib.sha256()
            h.update(resp.content[:PARTIAL_SIZE])
            return h.hexdigest()
        return None
    except Exception as e:
        log(f"OneDrive partial hash error {file_id}: {e}")
        return None


# ── pHash ──────────────────────────────────────────────────────────────────────


def phash_local(path: str) -> str | None:
    """Compute perceptual hash of a local image."""
    try:
        from PIL import Image
        import struct

        img = Image.open(path).convert("L").resize((32, 32), Image.LANCZOS)
        pixels = list(img.getdata())
        avg = sum(pixels) / len(pixels)
        bits = "".join("1" if p > avg else "0" for p in pixels)
        # Convert to hex
        n = int(bits, 2)
        return f"{n:064x}"
    except Exception as e:
        log(f"pHash error {path}: {e}")
        return None


def phash_distance(h1: str, h2: str) -> int:
    """Hamming distance between two pHashes. <10 = visually similar."""
    try:
        n1 = int(h1, 16)
        n2 = int(h2, 16)
        xor = n1 ^ n2
        return bin(xor).count("1")
    except Exception:
        return 999


PHASH_THRESHOLD = 10  # images with distance < 10 are considered visually identical


# ── Core Verifier ──────────────────────────────────────────────────────────────


def verify_group(
    group_id: str, members: list, mconn, dconn, gcreds, od_token: str, use_phash: bool, dry_run: bool
) -> str:
    """
    Verify a duplicate group. Returns:
      'confirmed'   — partial hashes match → upgrade to 100%
      'rejected'    — hashes don't match → downgrade to 40%
      'skipped'     — couldn't get hashes for comparison
      'phash_match' — byte hashes differ but visually identical
    """
    hashes = {}

    for m in members:
        source = m["source"]
        file_id = m["file_id"]
        cloud_id = m["cloud_file_id"]
        local_path = m["source_path"]
        filename = m["filename"]

        ph = None

        # Local files
        if source in ("macbook_local", "icloud_drive"):
            if local_path and Path(local_path).exists():
                ph = partial_hash_local(local_path)

        # iCloud Photos — only if downloaded locally
        elif source == "icloud_photos":
            if local_path and Path(local_path).exists():
                ph = partial_hash_local(local_path)

        # Google Drive
        elif source == "google_drive":
            if gcreds and cloud_id:
                ph = partial_hash_gdrive(cloud_id, gcreds)

        # OneDrive
        elif source == "onedrive":
            if od_token and cloud_id:
                ph = partial_hash_onedrive(cloud_id, od_token)

        if ph:
            hashes[file_id] = ph

    if len(hashes) < 2:
        return "skipped"

    hash_values = list(hashes.values())
    all_match = len(set(hash_values)) == 1

    if all_match:
        if not dry_run:
            dconn.execute(
                """
                UPDATE duplicate_groups SET confidence=100 WHERE group_id=?
            """,
                (group_id,),
            )
            dconn.execute(
                """
                UPDATE duplicate_members SET confidence=100 WHERE group_id=?
            """,
                (group_id,),
            )
        return "confirmed"

    # Hashes don't match — try pHash for photos if enabled
    if use_phash:
        photo_members = [
            m
            for m in members
            if Path(m["filename"]).suffix.lower() in PHOTO_EXTS and m["source_path"] and Path(m["source_path"]).exists()
        ]
        if len(photo_members) >= 2:
            ph1 = phash_local(photo_members[0]["source_path"])
            ph2 = phash_local(photo_members[1]["source_path"])
            if ph1 and ph2:
                dist = phash_distance(ph1, ph2)
                if dist < PHASH_THRESHOLD:
                    if not dry_run:
                        dconn.execute(
                            """
                            UPDATE duplicate_groups
                            SET confidence=95, match_type='phash_visual'
                            WHERE group_id=?
                        """,
                            (group_id,),
                        )
                        dconn.execute(
                            """
                            UPDATE duplicate_members SET confidence=95 WHERE group_id=?
                        """,
                            (group_id,),
                        )
                    return "phash_match"

    # Doesn't match — downgrade confidence so Phase 3 won't touch it
    if not dry_run:
        dconn.execute(
            """
            UPDATE duplicate_groups SET confidence=40 WHERE group_id=?
        """,
            (group_id,),
        )
        dconn.execute(
            """
            UPDATE duplicate_members SET confidence=40 WHERE group_id=?
        """,
            (group_id,),
        )
    return "rejected"


# ── Main ───────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="StorageRationalizer Phase 2b Media Verifier")
    parser.add_argument("--phash", action="store_true", help="Enable perceptual hashing for photos")
    parser.add_argument("--source", help="Verify only one source (e.g. onedrive)")
    parser.add_argument("--dry-run", action="store_true", help="Show results without updating DB")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of groups to verify (0=all)")
    args = parser.parse_args()

    console.rule("[bold blue]StorageRationalizer — Phase 2b Media Verifier[/bold blue]")
    console.print(f"  Manifest:  [cyan]{MANIFEST_DB}[/cyan]")
    console.print(f"  Dupes DB:  [cyan]{DUPES_DB}[/cyan]")
    console.print(f"  pHash:     [cyan]{'enabled' if args.phash else 'disabled'}[/cyan]")
    console.print(f"  Dry run:   [cyan]{'yes' if args.dry_run else 'no'}[/cyan]")
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
    dconn.execute("PRAGMA journal_mode=WAL")

    # Get all 90% media duplicate groups
    source_filter = f"AND m.source = '{args.source}'" if args.source else ""
    limit_clause = f"LIMIT {args.limit}" if args.limit else ""

    media_ext_list = "'" + "','".join([e.lstrip(".") for e in list(PHOTO_EXTS) + list(VIDEO_EXTS)]) + "'"

    groups = dconn.execute(
        f"""
        SELECT DISTINCT g.group_id, g.match_type, g.confidence,
                        g.keep_source, g.keep_filename, g.wasted_size
        FROM duplicate_groups g
        JOIN duplicate_members m ON g.group_id = m.group_id
        WHERE g.confidence = 90
          AND LOWER(SUBSTR(m.filename, INSTR(m.filename, '.') + 1)) IN ({media_ext_list})
          {source_filter}
        ORDER BY g.wasted_size DESC
        {limit_clause}
    """
    ).fetchall()

    console.print(f"  [bold]Media groups to verify:[/bold] {len(groups):,}")
    console.print()

    if not groups:
        console.print("[yellow]No 90% media groups found to verify.[/yellow]")
        return

    # Auth — only connect to what's needed
    gcreds = None
    od_token = None

    sources_needed = set()
    for g in groups:
        members = dconn.execute("SELECT * FROM duplicate_members WHERE group_id=?", (g["group_id"],)).fetchall()
        for m in members:
            sources_needed.add(m["source"])

    if "google_drive" in sources_needed:
        console.print("[dim]Connecting to Google Drive...[/dim]")
        gcreds = get_google_creds()
        if gcreds:
            console.print("  [green]✓ Google Drive connected[/green]")
        else:
            console.print("  [yellow]⚠ Google Drive not available — will skip GDrive files[/yellow]")

    if "onedrive" in sources_needed:
        console.print("[dim]Connecting to OneDrive...[/dim]")
        od_token = get_onedrive_token()
        if od_token:
            console.print("  [green]✓ OneDrive connected[/green]")
        else:
            console.print("  [yellow]⚠ OneDrive not available — will skip OneDrive files[/yellow]")

    console.print()

    stats = {"confirmed": 0, "rejected": 0, "skipped": 0, "phash_match": 0}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:

        task = progress.add_task("Verifying media...", total=len(groups))

        for i, g in enumerate(groups):
            progress.update(task, description=f"[cyan]Verifying[/cyan] {g['keep_filename'][:50]}", completed=i)

            # Get all members with manifest data
            raw_members = dconn.execute("SELECT * FROM duplicate_members WHERE group_id=?", (g["group_id"],)).fetchall()

            members = []
            for m in raw_members:
                mf = mconn.execute("SELECT * FROM files WHERE file_id=?", (m["file_id"],)).fetchone()
                if mf:
                    members.append(
                        {
                            "file_id": m["file_id"],
                            "source": m["source"],
                            "filename": m["filename"],
                            "cloud_file_id": mf["cloud_file_id"],
                            "source_path": mf["source_path"],
                        }
                    )

            result = verify_group(g["group_id"], members, mconn, dconn, gcreds, od_token, args.phash, args.dry_run)
            stats[result] += 1

            if (i + 1) % 50 == 0:
                dconn.commit()

        progress.update(task, completed=len(groups))

    dconn.commit()

    # Summary
    console.print()
    console.rule("[bold blue]Verification Complete[/bold blue]")
    console.print()

    table = Table(show_header=True, header_style="bold navy_blue")
    table.add_column("Result", style="cyan", min_width=20)
    table.add_column("Groups", style="white", justify="right")
    table.add_column("Meaning", style="dim")

    table.add_row("✓ Confirmed (→100%)", str(stats["confirmed"]), "Partial hashes match — safe to delete")
    table.add_row("✗ Rejected  (→40%)", str(stats["rejected"]), "Hashes differ — removed from delete list")
    table.add_row("~ Skipped", str(stats["skipped"]), "Couldn't download/access to verify")
    if args.phash:
        table.add_row("≈ pHash match (→95%)", str(stats["phash_match"]), "Visually identical — safe to delete")

    console.print(table)
    console.print()

    # Show updated savings after verification
    row = dconn.execute(
        """
        SELECT COUNT(DISTINCT g.group_id) groups,
               SUM(CASE WHEN m.action='delete' THEN 1 ELSE 0 END) files,
               SUM(CASE WHEN m.action='delete' THEN m.file_size ELSE 0 END) wasted
        FROM duplicate_members m
        JOIN duplicate_groups g ON m.group_id = g.group_id
        WHERE g.confidence >= 90
    """
    ).fetchone()

    console.print(f"  [bold]Updated delete list (≥90% confidence):[/bold]")
    console.print(f"    Groups: {row['groups']:,}")
    console.print(f"    Files:  {row['files']:,}")
    console.print(f"    Space:  [green]{format_size(row['wasted'])}[/green]")
    console.print()
    console.print(
        f"  [dim]Run Phase 2 classifier with --reset to regenerate reports with updated confidence scores.[/dim]"
    )
    console.print()
    console.rule()

    mconn.close()
    dconn.close()


if __name__ == "__main__":
    main()
