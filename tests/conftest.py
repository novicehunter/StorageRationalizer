"""Shared pytest fixtures for StorageRationalizer tests."""

import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

# Make project root importable
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ── In-memory DB helpers ───────────────────────────────────────────────────────


def _create_manifest_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            file_id TEXT PRIMARY KEY,
            source TEXT,
            source_path TEXT,
            cloud_file_id TEXT,
            filename TEXT,
            file_size INTEGER,
            sha256_hash TEXT,
            md5_hash TEXT,
            is_photo INTEGER DEFAULT 0,
            is_video INTEGER DEFAULT 0,
            is_document INTEGER DEFAULT 0,
            is_downloaded INTEGER DEFAULT 1,
            created_at TEXT,
            modified_at TEXT,
            scanned_at TEXT
        )
    """
    )
    conn.commit()


def _create_dupes_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS duplicate_groups (
            group_id TEXT PRIMARY KEY,
            match_type TEXT,
            confidence INTEGER,
            wasted_size INTEGER,
            keep_file_id TEXT,
            created_at TEXT
        )
    """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS duplicate_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT,
            file_id TEXT,
            source TEXT,
            action TEXT DEFAULT 'delete'
        )
    """
    )
    conn.commit()


@pytest.fixture
def manifest_conn():
    """In-memory manifest DB with schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _create_manifest_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def dupes_conn():
    """In-memory duplicates DB with schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _create_dupes_schema(conn)
    yield conn
    conn.close()


# ── Sample file record factory ─────────────────────────────────────────────────


def make_file(
    source="macbook_local",
    filename="test.pdf",
    file_size=10240,
    sha256_hash=None,
    source_path=None,
    cloud_file_id=None,
    is_photo=0,
    is_video=0,
    is_document=1,
) -> dict:
    fid = str(uuid.uuid4())
    return {
        "file_id": fid,
        "source": source,
        "source_path": source_path or f"/fake/{source}/{fid}/{filename}",
        "cloud_file_id": cloud_file_id,
        "filename": filename,
        "file_size": file_size,
        "sha256_hash": sha256_hash or "aabbccdd" * 8,
        "md5_hash": None,
        "is_photo": is_photo,
        "is_video": is_video,
        "is_document": is_document,
        "is_downloaded": 1,
        "created_at": "2024-01-01T00:00:00+00:00",
        "modified_at": "2024-01-01T00:00:00+00:00",
        "scanned_at": "2024-01-01T00:00:00+00:00",
    }


def insert_file(conn: sqlite3.Connection, record: dict) -> None:
    cols = ", ".join(record.keys())
    vals = ", ".join(["?"] * len(record))
    conn.execute(f"INSERT OR REPLACE INTO files ({cols}) VALUES ({vals})", list(record.values()))
    conn.commit()


@pytest.fixture
def sample_files(manifest_conn):
    """Manifest DB pre-loaded with a small set of cross-source files."""
    records = [
        make_file(source="google_drive", filename="report.pdf", sha256_hash="aa" * 32, cloud_file_id="gd-1"),
        make_file(source="onedrive", filename="report.pdf", sha256_hash="aa" * 32, cloud_file_id="od-1"),
        make_file(source="macbook_local", filename="report.pdf", sha256_hash="aa" * 32),
        make_file(source="macbook_local", filename="unique.txt", sha256_hash="bb" * 32),
    ]
    for r in records:
        insert_file(manifest_conn, r)
    return manifest_conn, records
