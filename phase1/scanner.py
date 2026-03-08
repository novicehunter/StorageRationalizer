#!/usr/bin/env python3
"""
StorageRationalizer — Phase 1 Scanner v2
Scans all sources and builds a unified file manifest database.
Never downloads files. Metadata only.

Run order:
  1. MacBook Local       — filesystem walk
  2. iCloud Drive        — filesystem walk (documents/files only)
  3. iCloud Photos       — osxphotos reads Photos.app DB (all assets, no download needed)
  4. Google Drive        — Google Drive API v3
  5. Google Photos       — Photos Library API
  6. OneDrive            — Microsoft Graph API

Usage:
    python3 scanner.py                                              # all sources
    python3 scanner.py --sources local icloud_drive icloud_photos  # apple only
    python3 scanner.py --sources google_drive google_photos onedrive
    python3 scanner.py --reset                                      # wipe and restart
"""

import os, sys, json, hashlib, sqlite3, uuid, argparse, mimetypes
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

console = Console()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE = Path.home() / "Desktop" / "StorageRationalizer"
CREDS_DIR = BASE / "credentials"
MANIFEST_DIR = BASE / "manifests"
LOGS_DIR = BASE / "logs"
MANIFEST_DB = MANIFEST_DIR / "manifest.db"
ICLOUD_DRIVE_PATH = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
PHOTOS_LIBRARY = Path.home() / "Pictures" / "Photos Library.photoslibrary"

LOCAL_SCAN_PATHS = [
    Path.home() / "Documents",
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Pictures",
    Path.home() / "Movies",
    Path.home() / "Music",
]

PHOTO_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".heic",
    ".heif",
    ".tiff",
    ".tif",
    ".bmp",
    ".webp",
    ".raw",
    ".cr2",
    ".nef",
    ".arw",
    ".dng",
}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".wmv", ".flv", ".webm", ".3gp", ".mts", ".m2ts"}
DOC_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".md", ".pages", ".numbers", ".key"}
SKIP_EXTS = {".ds_store", ".localized", ".tmp", ".temp", ".cache", ".log", ".icloud"}
SKIP_DIRS = {".git", "node_modules", ".Trash", "__pycache__", ".cache", "Photos Library.photoslibrary"}


# ── Database ───────────────────────────────────────────────────────────────────
def init_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            file_id          TEXT PRIMARY KEY,
            source           TEXT NOT NULL,
            source_path      TEXT,
            cloud_file_id    TEXT,
            filename         TEXT NOT NULL,
            file_ext         TEXT,
            file_size        INTEGER,
            mime_type        TEXT,
            sha256_hash      TEXT,
            md5_hash         TEXT,
            sha1_hash        TEXT,
            quick_xor_hash   TEXT,
            created_at       TEXT,
            modified_at      TEXT,
            exif_date        TEXT,
            latitude         REAL,
            longitude        REAL,
            width            INTEGER,
            height           INTEGER,
            is_photo         INTEGER DEFAULT 0,
            is_video         INTEGER DEFAULT 0,
            is_document      INTEGER DEFAULT 0,
            is_downloaded    INTEGER DEFAULT 1,
            is_favorite      INTEGER DEFAULT 0,
            is_edited        INTEGER DEFAULT 0,
            is_live_photo    INTEGER DEFAULT 0,
            is_screenshot    INTEGER DEFAULT 0,
            is_selfie        INTEGER DEFAULT 0,
            is_portrait      INTEGER DEFAULT 0,
            media_type_flags TEXT,
            album_name       TEXT,
            parent_folder    TEXT,
            drive_name       TEXT,
            raw_metadata     TEXT,
            scanned_at       TEXT NOT NULL,
            scan_error       TEXT
        )
    """
    )
    for idx in ["source", "filename", "sha256_hash", "md5_hash", "file_size", "exif_date"]:
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{idx} ON files({idx})")
    conn.commit()
    return conn


def already_scanned(conn, source, identifier):
    return (
        conn.execute(
            "SELECT 1 FROM files WHERE source=? AND (source_path=? OR cloud_file_id=?) LIMIT 1",
            (source, identifier, identifier),
        ).fetchone()
        is not None
    )


def insert_file(conn, record):
    cols = ", ".join(record.keys())
    vals = ", ".join(["?"] * len(record))
    conn.execute(f"INSERT OR REPLACE INTO files ({cols}) VALUES ({vals})", list(record.values()))


# ── Helpers ────────────────────────────────────────────────────────────────────
def now_iso():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path):
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def categorize(ext):
    ext = ext.lower()
    return (1 if ext in PHOTO_EXTS else 0, 1 if ext in VIDEO_EXTS else 0, 1 if ext in DOC_EXTS else 0)


def should_skip(path):
    for part in path.parts:
        if part in SKIP_DIRS:
            return True
    return path.suffix.lower() in SKIP_EXTS


def format_size(b):
    if not b:
        return "0 B"
    b = int(b)
    for u in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {u}"
        b /= 1024
    return f"{b:.1f} PB"


def log_error(source, msg):
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOGS_DIR / f"scan_errors_{datetime.now().strftime('%Y%m%d')}.log", "a") as f:
        f.write(f"[{now_iso()}] [{source}] {msg}\n")


def safe_iso(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc).isoformat()
        return dt.isoformat()
    return str(dt)


def base_record(source):
    return {
        "file_id": str(uuid.uuid4()),
        "source": source,
        "source_path": None,
        "cloud_file_id": None,
        "filename": "",
        "file_ext": "",
        "file_size": None,
        "mime_type": "",
        "sha256_hash": None,
        "md5_hash": None,
        "sha1_hash": None,
        "quick_xor_hash": None,
        "created_at": None,
        "modified_at": None,
        "exif_date": None,
        "latitude": None,
        "longitude": None,
        "width": None,
        "height": None,
        "is_photo": 0,
        "is_video": 0,
        "is_document": 0,
        "is_downloaded": 1,
        "is_favorite": 0,
        "is_edited": 0,
        "is_live_photo": 0,
        "is_screenshot": 0,
        "is_selfie": 0,
        "is_portrait": 0,
        "media_type_flags": None,
        "album_name": None,
        "parent_folder": None,
        "drive_name": None,
        "raw_metadata": None,
        "scanned_at": now_iso(),
        "scan_error": None,
    }


# ── Scanner 1: MacBook Local ───────────────────────────────────────────────────
def scan_local(conn, progress, task):
    stats = {"found": 0, "new": 0, "errors": 0}
    for root in LOCAL_SCAN_PATHS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_dir() or should_skip(path):
                continue
            # Skip Photos library and iCloud Drive (handled by other scanners)
            try:
                path.relative_to(PHOTOS_LIBRARY)
                continue
            except ValueError:
                pass
            try:
                path.relative_to(ICLOUD_DRIVE_PATH)
                continue
            except ValueError:
                pass

            stats["found"] += 1
            progress.update(task, description=f"[cyan]MacBook Local[/cyan] {path.name[:55]}")
            sp = str(path)
            if already_scanned(conn, "macbook_local", sp):
                continue
            try:
                stat = path.stat()
                ext = path.suffix.lower()
                p, v, d = categorize(ext)
                r = base_record("macbook_local")
                r.update(
                    {
                        "source_path": sp,
                        "filename": path.name,
                        "file_ext": ext,
                        "file_size": stat.st_size,
                        "mime_type": mimetypes.guess_type(sp)[0] or "",
                        "sha256_hash": sha256_file(path) if stat.st_size < 500 * 1024 * 1024 else None,
                        "created_at": (
                            datetime.fromtimestamp(stat.st_birthtime, timezone.utc).isoformat()
                            if hasattr(stat, "st_birthtime")
                            else None
                        ),
                        "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                        "is_photo": p,
                        "is_video": v,
                        "is_document": d,
                        "parent_folder": str(path.parent),
                    }
                )
                insert_file(conn, r)
                stats["new"] += 1
                if stats["new"] % 100 == 0:
                    conn.commit()
            except Exception as e:
                stats["errors"] += 1
                log_error("macbook_local", f"{path}: {e}")
    conn.commit()
    return stats


# ── Scanner 2: iCloud Drive (files/documents) ──────────────────────────────────
def scan_icloud_drive(conn, progress, task):
    stats = {"found": 0, "new": 0, "errors": 0}
    if not ICLOUD_DRIVE_PATH.exists():
        console.print(f"[yellow]iCloud Drive path not found: {ICLOUD_DRIVE_PATH}[/yellow]")
        return stats
    for path in ICLOUD_DRIVE_PATH.rglob("*"):
        if path.is_dir() or should_skip(path) or path.suffix == ".icloud":
            continue
        stats["found"] += 1
        progress.update(task, description=f"[blue]iCloud Drive[/blue] {path.name[:55]}")
        sp = str(path)
        if already_scanned(conn, "icloud_drive", sp):
            continue
        try:
            stat = path.stat()
            ext = path.suffix.lower()
            p, v, d = categorize(ext)
            try:
                rel = str(path.relative_to(ICLOUD_DRIVE_PATH))
                parent = rel.rsplit("/", 1)[0] if "/" in rel else ""
            except ValueError:
                parent = ""
            r = base_record("icloud_drive")
            r.update(
                {
                    "source_path": sp,
                    "filename": path.name,
                    "file_ext": ext,
                    "file_size": stat.st_size,
                    "mime_type": mimetypes.guess_type(sp)[0] or "",
                    "sha256_hash": sha256_file(path) if stat.st_size < 500 * 1024 * 1024 else None,
                    "created_at": (
                        datetime.fromtimestamp(stat.st_birthtime, timezone.utc).isoformat()
                        if hasattr(stat, "st_birthtime")
                        else None
                    ),
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                    "is_photo": p,
                    "is_video": v,
                    "is_document": d,
                    "parent_folder": parent,
                }
            )
            insert_file(conn, r)
            stats["new"] += 1
            if stats["new"] % 100 == 0:
                conn.commit()
        except Exception as e:
            stats["errors"] += 1
            log_error("icloud_drive", f"{path}: {e}")
    conn.commit()
    return stats


# ── Scanner 3: iCloud Photos via osxphotos ────────────────────────────────────
def scan_icloud_photos(conn, progress, task):
    stats = {"found": 0, "new": 0, "errors": 0}
    try:
        import osxphotos
    except ImportError:
        console.print("[red]osxphotos not installed. Run: pip3 install osxphotos --break-system-packages[/red]")
        return stats
    if not PHOTOS_LIBRARY.exists():
        console.print(f"[yellow]Photos library not found: {PHOTOS_LIBRARY}[/yellow]")
        return stats

    progress.update(task, description="[magenta]iCloud Photos[/magenta] Opening library (may take 30s)...")
    try:
        db = osxphotos.PhotosDB(str(PHOTOS_LIBRARY))
    except Exception as e:
        console.print(f"[red]Failed to open Photos library: {e}[/red]")
        log_error("icloud_photos", str(e))
        return stats

    photos = db.photos(movies=True)
    total = len(photos)
    progress.update(
        task, total=total, completed=0, description=f"[magenta]iCloud Photos[/magenta] {total:,} assets — scanning..."
    )

    for i, photo in enumerate(photos):
        stats["found"] += 1
        try:
            uid = photo.uuid
            if already_scanned(conn, "icloud_photos", uid):
                progress.update(task, completed=i + 1)
                continue

            flags = []
            if getattr(photo, "live_photo", False):
                flags.append("live_photo")
            if getattr(photo, "screenshot", False):
                flags.append("screenshot")
            if getattr(photo, "selfie", False):
                flags.append("selfie")
            if getattr(photo, "portrait", False):
                flags.append("portrait")
            if getattr(photo, "hdr", False):
                flags.append("hdr")
            if getattr(photo, "panorama", False):
                flags.append("panorama")
            if getattr(photo, "slow_mo", False):
                flags.append("slow_mo")
            if getattr(photo, "time_lapse", False):
                flags.append("time_lapse")
            if getattr(photo, "burst", False):
                flags.append("burst")

            albums = []
            try:
                albums = [a.title for a in photo.album_info] if photo.album_info else []
            except Exception:
                pass

            lat, lon = None, None
            try:
                if photo.location:
                    lat, lon = photo.location[0], photo.location[1]
            except Exception:
                pass

            filename = photo.original_filename or photo.filename or ""
            ext = Path(filename).suffix.lower()
            is_video = getattr(photo, "isvideostr", None) or (ext in VIDEO_EXTS)
            is_photo = not is_video

            local_path = photo.path
            size, sha = None, None
            if local_path and Path(local_path).exists():
                try:
                    size = Path(local_path).stat().st_size
                    if size and size < 500 * 1024 * 1024:
                        sha = sha256_file(Path(local_path))
                except Exception:
                    pass

            is_downloaded = 1 if (local_path and Path(local_path).exists()) else 0

            r = base_record("icloud_photos")
            r.update(
                {
                    "source_path": local_path or None,
                    "cloud_file_id": uid,
                    "filename": filename,
                    "file_ext": ext,
                    "file_size": size,
                    "mime_type": getattr(photo, "uti", "") or "",
                    "sha256_hash": sha,
                    "created_at": safe_iso(getattr(photo, "date_added", None)),
                    "modified_at": safe_iso(getattr(photo, "date_modified", None)),
                    "exif_date": safe_iso(getattr(photo, "date", None)),
                    "latitude": lat,
                    "longitude": lon,
                    "width": getattr(photo, "width", None),
                    "height": getattr(photo, "height", None),
                    "is_photo": 1 if is_photo else 0,
                    "is_video": 1 if is_video else 0,
                    "is_document": 0,
                    "is_downloaded": is_downloaded,
                    "is_favorite": 1 if getattr(photo, "favorite", False) else 0,
                    "is_edited": 1 if getattr(photo, "hasadjustments", False) else 0,
                    "is_live_photo": 1 if getattr(photo, "live_photo", False) else 0,
                    "is_screenshot": 1 if getattr(photo, "screenshot", False) else 0,
                    "is_selfie": 1 if getattr(photo, "selfie", False) else 0,
                    "is_portrait": 1 if getattr(photo, "portrait", False) else 0,
                    "media_type_flags": ",".join(flags) if flags else None,
                    "album_name": ",".join(albums) if albums else None,
                }
            )
            insert_file(conn, r)
            stats["new"] += 1
            if stats["new"] % 200 == 0:
                conn.commit()

        except Exception as e:
            stats["errors"] += 1
            log_error("icloud_photos", f"{getattr(photo,'uuid','?')}: {e}")

        progress.update(task, completed=i + 1)

    conn.commit()
    return stats


# ── Scanner 4: Google Drive ────────────────────────────────────────────────────
def scan_google_drive(conn, progress, task):
    stats = {"found": 0, "new": 0, "errors": 0}
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        console.print("[red]Google API libraries not installed.[/red]")
        return stats

    creds_file = CREDS_DIR / "google_credentials.json"
    token_file = CREDS_DIR / "google_token.json"
    SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

    if not creds_file.exists():
        console.print(f"[red]Not found: {creds_file}[/red]")
        return stats

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())

    service = build("drive", "v3", credentials=creds)
    fields = "nextPageToken, files(id,name,mimeType,size,md5Checksum,createdTime,modifiedTime,parents,driveId,imageMediaMetadata,videoMediaMetadata,trashed)"
    pt = None
    while True:
        try:
            resp = (
                service.files()
                .list(
                    pageSize=1000,
                    fields=fields,
                    pageToken=pt,
                    q="trashed=false",
                    includeItemsFromAllDrives=True,
                    supportsAllDrives=True,
                    corpora="allDrives",
                )
                .execute()
            )
        except Exception as e:
            log_error("google_drive", str(e))
            break

        for f in resp.get("files", []):
            mime = f.get("mimeType", "")
            if mime == "application/vnd.google-apps.folder":
                continue
            if mime.startswith("application/vnd.google-apps."):
                continue
            stats["found"] += 1
            progress.update(task, description=f"[green]Google Drive[/green] {f.get('name','')[:55]}")
            fid = f.get("id")
            if already_scanned(conn, "google_drive", fid):
                continue
            try:
                name = f.get("name", "")
                ext = Path(name).suffix.lower()
                p, v, d = categorize(ext)
                im = f.get("imageMediaMetadata", {})
                vm = f.get("videoMediaMetadata", {})
                r = base_record("google_drive")
                r.update(
                    {
                        "cloud_file_id": fid,
                        "filename": name,
                        "file_ext": ext,
                        "file_size": int(f["size"]) if f.get("size") else None,
                        "mime_type": mime,
                        "md5_hash": f.get("md5Checksum"),
                        "created_at": f.get("createdTime"),
                        "modified_at": f.get("modifiedTime"),
                        "exif_date": im.get("time"),
                        "width": im.get("width") or vm.get("width"),
                        "height": im.get("height") or vm.get("height"),
                        "is_photo": p,
                        "is_video": v,
                        "is_document": d,
                        "is_downloaded": 0,
                        "parent_folder": json.dumps(f.get("parents", [])),
                        "drive_name": f.get("driveId"),
                        "raw_metadata": json.dumps(f),
                    }
                )
                insert_file(conn, r)
                stats["new"] += 1
                if stats["new"] % 200 == 0:
                    conn.commit()
            except Exception as e:
                stats["errors"] += 1
                log_error("google_drive", f"{fid}: {e}")

        pt = resp.get("nextPageToken")
        if not pt:
            break
    conn.commit()
    return stats


# ── Scanner 5: Google Photos ───────────────────────────────────────────────────
def scan_google_photos(conn, progress, task):
    stats = {"found": 0, "new": 0, "errors": 0}
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        import requests as rl
    except ImportError:
        console.print("[red]Google API libraries not installed.[/red]")
        return stats

    SCOPES = [
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/photoslibrary.readonly",
    ]
    creds_file = CREDS_DIR / "google_credentials.json"
    token_file = CREDS_DIR / "google_token.json"

    if not creds_file.exists():
        console.print(f"[red]Not found: {creds_file}[/red]")
        return stats

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, "w") as f:
            f.write(creds.to_json())

    headers = {"Authorization": f"Bearer {creds.token}"}
    pt = None
    while True:
        try:
            params = {"pageSize": 100}
            if pt:
                params["pageToken"] = pt
            resp = rl.get(
                "https://photoslibrary.googleapis.com/v1/mediaItems", headers=headers, params=params, timeout=30
            )
            if resp.status_code == 401:
                creds.refresh(Request())
                headers = {"Authorization": f"Bearer {creds.token}"}
                with open(token_file, "w") as f:
                    f.write(creds.to_json())
                continue
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log_error("google_photos", str(e))
            break

        for item in data.get("mediaItems", []):
            stats["found"] += 1
            progress.update(task, description=f"[magenta]Google Photos[/magenta] {item.get('filename','')[:55]}")
            iid = item.get("id")
            if already_scanned(conn, "google_photos", iid):
                continue
            try:
                meta = item.get("mediaMetadata", {})
                mime = item.get("mimeType", "")
                name = item.get("filename", "")
                ext = Path(name).suffix.lower()
                r = base_record("google_photos")
                r.update(
                    {
                        "cloud_file_id": iid,
                        "filename": name,
                        "file_ext": ext,
                        "mime_type": mime,
                        "created_at": meta.get("creationTime"),
                        "exif_date": meta.get("creationTime"),
                        "width": int(meta["width"]) if meta.get("width") else None,
                        "height": int(meta["height"]) if meta.get("height") else None,
                        "is_photo": 1 if "image" in mime else 0,
                        "is_video": 1 if "video" in mime else 0,
                        "is_downloaded": 0,
                        "raw_metadata": json.dumps(item),
                    }
                )
                insert_file(conn, r)
                stats["new"] += 1
                if stats["new"] % 200 == 0:
                    conn.commit()
            except Exception as e:
                stats["errors"] += 1
                log_error("google_photos", f"{iid}: {e}")

        pt = data.get("nextPageToken")
        if not pt:
            break
    conn.commit()
    return stats


# ── Scanner 6: OneDrive ────────────────────────────────────────────────────────
def scan_onedrive(conn, progress, task):
    stats = {"found": 0, "new": 0, "errors": 0}
    try:
        import msal
        import requests as rl
    except ImportError:
        console.print("[red]msal not installed.[/red]")
        return stats

    creds_file = CREDS_DIR / "onedrive_credentials.txt"
    token_file = CREDS_DIR / "onedrive_token.json"
    if not creds_file.exists():
        console.print(f"[red]Not found: {creds_file}[/red]")
        return stats

    creds = {}
    with open(creds_file) as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                creds[k.strip()] = v.strip()

    client_id = creds.get("CLIENT_ID")
    tenant_id = creds.get("TENANT_ID")
    client_secret = creds.get("CLIENT_SECRET")
    if not all([client_id, tenant_id, client_secret]):
        console.print("[red]OneDrive credentials file incomplete.[/red]")
        return stats

    app = msal.ConfidentialClientApplication(
        client_id, authority=f"https://login.microsoftonline.com/{tenant_id}", client_credential=client_secret
    )

    token = None
    if token_file.exists():
        with open(token_file) as f:
            cached = json.load(f)
            if cached.get("expires_at", 0) > datetime.now().timestamp() + 60:
                token = cached.get("access_token")
    if not token:
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        if "access_token" not in result:
            console.print(f"[red]OneDrive auth failed: {result.get('error_description')}[/red]")
            return stats
        token = result["access_token"]
        with open(token_file, "w") as f:
            json.dump(
                {"access_token": token, "expires_at": datetime.now().timestamp() + result.get("expires_in", 3600)}, f
            )

    headers = {"Authorization": f"Bearer {token}"}
    base_url = "https://graph.microsoft.com/v1.0"

    def scan_folder(url, folder_path):
        while url:
            try:
                resp = rl.get(url, headers=headers, timeout=30)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                log_error("onedrive", f"{folder_path}: {e}")
                return

            for item in data.get("value", []):
                if "folder" in item:
                    scan_folder(f"{base_url}/me/drive/items/{item['id']}/children", f"{folder_path}/{item['name']}")
                    continue
                stats["found"] += 1
                progress.update(task, description=f"[yellow]OneDrive[/yellow] {item.get('name','')[:55]}")
                iid = item.get("id")
                if already_scanned(conn, "onedrive", iid):
                    continue
                try:
                    name = item.get("name", "")
                    ext = Path(name).suffix.lower()
                    p, v, d = categorize(ext)
                    hashes = item.get("file", {}).get("hashes", {})
                    im = item.get("photo", {})
                    vm = item.get("video", {})
                    fs = item.get("fileSystemInfo", {})
                    r = base_record("onedrive")
                    r.update(
                        {
                            "cloud_file_id": iid,
                            "filename": name,
                            "file_ext": ext,
                            "file_size": item.get("size"),
                            "mime_type": item.get("file", {}).get("mimeType", ""),
                            "md5_hash": hashes.get("sha256Hash", "").lower() or None,
                            "sha1_hash": hashes.get("sha1Hash", "").lower() or None,
                            "quick_xor_hash": hashes.get("quickXorHash") or None,
                            "created_at": fs.get("createdDateTime") or item.get("createdDateTime"),
                            "modified_at": fs.get("lastModifiedDateTime") or item.get("lastModifiedDateTime"),
                            "exif_date": im.get("takenDateTime"),
                            "latitude": im.get("latitude"),
                            "longitude": im.get("longitude"),
                            "width": im.get("width") or vm.get("width"),
                            "height": im.get("height") or vm.get("height"),
                            "is_photo": p,
                            "is_video": v,
                            "is_document": d,
                            "is_downloaded": 0,
                            "parent_folder": folder_path,
                            "raw_metadata": json.dumps(item),
                        }
                    )
                    insert_file(conn, r)
                    stats["new"] += 1
                    if stats["new"] % 200 == 0:
                        conn.commit()
                except Exception as e:
                    stats["errors"] += 1
                    log_error("onedrive", f"{iid}: {e}")
            url = data.get("@odata.nextLink")

    scan_folder(f"{base_url}/me/drive/root/children", "/OneDrive")
    conn.commit()
    return stats


# ── Summary ────────────────────────────────────────────────────────────────────
def print_summary(conn):
    console.print()
    console.rule("[bold blue]Phase 1 Scan Complete[/bold blue]")
    console.print()

    table = Table(title="Files by Source", show_header=True, header_style="bold navy_blue")
    table.add_column("Source", style="cyan", min_width=18)
    table.add_column("Total", style="white", justify="right")
    table.add_column("Photos", style="green", justify="right")
    table.add_column("Videos", style="yellow", justify="right")
    table.add_column("Docs", style="blue", justify="right")
    table.add_column("Cloud-only", style="red", justify="right")
    table.add_column("Size", style="white", justify="right")

    total_files = 0
    for row in conn.execute(
        """
        SELECT source, COUNT(*) total,
               SUM(is_photo) photos, SUM(is_video) videos, SUM(is_document) docs,
               SUM(CASE WHEN is_downloaded=0 THEN 1 ELSE 0 END) cloud_only,
               SUM(file_size) sz
        FROM files GROUP BY source ORDER BY total DESC
    """
    ):
        table.add_row(
            row["source"],
            str(row["total"]),
            str(row["photos"] or 0),
            str(row["videos"] or 0),
            str(row["docs"] or 0),
            str(row["cloud_only"] or 0),
            format_size(row["sz"]),
        )
        total_files += row["total"]

    console.print(table)
    console.print()

    total_size = conn.execute("SELECT SUM(file_size) FROM files").fetchone()[0]
    console.print(f"  [bold]Total files:[/bold]  {total_files:,}")
    console.print(f"  [bold]Total size:[/bold]   {format_size(total_size)}")
    console.print()

    # iCloud Photos breakdown
    row = conn.execute(
        """
        SELECT COUNT(*) t, SUM(is_downloaded) dl, SUM(is_favorite) fav,
               SUM(is_live_photo) live, SUM(is_screenshot) ss,
               SUM(is_selfie) sf, SUM(is_portrait) pt, SUM(is_edited) ed
        FROM files WHERE source='icloud_photos'
    """
    ).fetchone()
    if row and row["t"]:
        console.print(f"  [bold magenta]iCloud Photos breakdown:[/bold magenta]")
        console.print(
            f"    Total: {row['t']:,}  |  Downloaded locally: {row['dl']:,}  |  Cloud-only: {row['t']-row['dl']:,}"
        )
        console.print(
            f"    Favorites: {row['fav']}  |  Live Photos: {row['live']}  |  Selfies: {row['sf']}  |  Portraits: {row['pt']}  |  Screenshots: {row['ss']}  |  Edited: {row['ed']}"
        )
        console.print()

    dups = conn.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT filename, file_size FROM files
            WHERE file_size IS NOT NULL AND file_size > 0
            GROUP BY filename, file_size HAVING COUNT(DISTINCT source) > 1)
    """
    ).fetchone()[0]
    console.print(f"  [bold yellow]Potential cross-source duplicates:[/bold yellow] {dups:,}")
    console.print(f"  [bold]Manifest:[/bold] {MANIFEST_DB}")
    console.print()
    console.rule()


# ── Main ───────────────────────────────────────────────────────────────────────
SCANNER_ORDER = ["local", "icloud_drive", "icloud_photos", "google_drive", "google_photos", "onedrive"]
SCANNERS = {
    "local": ("MacBook Local", scan_local),
    "icloud_drive": ("iCloud Drive", scan_icloud_drive),
    "icloud_photos": ("iCloud Photos", scan_icloud_photos),
    "google_drive": ("Google Drive", scan_google_drive),
    "google_photos": ("Google Photos", scan_google_photos),
    "onedrive": ("OneDrive", scan_onedrive),
}


def main():
    parser = argparse.ArgumentParser(description="StorageRationalizer Phase 1 Scanner v2")
    parser.add_argument("--sources", nargs="+", choices=list(SCANNERS.keys()) + ["all"], default=["all"])
    parser.add_argument("--reset", action="store_true", help="Wipe manifest and start fresh")
    args = parser.parse_args()

    sources = args.sources
    if "all" in sources:
        sources = SCANNER_ORDER
    else:
        sources = [s for s in SCANNER_ORDER if s in sources]

    console.rule("[bold blue]StorageRationalizer — Phase 1 Scanner v2[/bold blue]")
    console.print(f"  Run order: [cyan]{' → '.join(sources)}[/cyan]")
    console.print(f"  Manifest:  [cyan]{MANIFEST_DB}[/cyan]")
    console.print()

    if args.reset and MANIFEST_DB.exists():
        MANIFEST_DB.unlink()
        console.print("[yellow]Manifest wiped — starting fresh[/yellow]\n")

    conn = init_db(MANIFEST_DB)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        for key in sources:
            name, fn = SCANNERS[key]
            task = progress.add_task(f"Scanning {name}...", total=None, completed=0)
            try:
                s = fn(conn, progress, task)
                progress.update(
                    task,
                    description=f"[green]✓ {name}[/green] — {s['new']:,} new  {s['errors']} errors",
                    completed=s["found"],
                    total=max(s["found"], 1),
                )
            except Exception as e:
                progress.update(task, description=f"[red]✗ {name} — {e}[/red]")
                log_error(key, f"Scanner crashed: {e}")

    print_summary(conn)
    conn.close()


if __name__ == "__main__":
    main()
