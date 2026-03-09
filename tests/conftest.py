import sqlite3
import uuid

import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from datetime import datetime, timezone


def make_file(**kwargs):
    """Create a minimal file record dict for testing."""
    defaults = {
        "file_id": str(uuid.uuid4()),
        "source": "macbook_local",
        "source_path": None,
        "cloud_file_id": None,
        "filename": "test.pdf",
        "file_ext": ".pdf",
        "file_size": 1024,
        "mime_type": "application/pdf",
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
        "is_document": 1,
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
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "scan_error": None,
    }
    defaults.update(kwargs)
    return defaults


def insert_file(conn, record):
    """Insert a file record into the manifest DB."""
    cols = ", ".join(record.keys())
    vals = ", ".join(["?"] * len(record))
    conn.execute(
        f"INSERT OR REPLACE INTO files ({cols}) VALUES ({vals})",
        list(record.values()),
    )
    conn.commit()


_CREATE_FILES_TABLE = """
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


@pytest.fixture
def manifest_conn():
    """In-memory SQLite manifest DB for testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(_CREATE_FILES_TABLE)
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def sample_files(manifest_conn):
    """Pre-populated manifest DB with 4 sample files."""
    records = [
        make_file(
            source="google_drive",
            cloud_file_id="gd1",
            filename="report.pdf",
            sha256_hash="aa" * 32,
            file_size=2048,
        ),
        make_file(
            source="onedrive",
            cloud_file_id="od1",
            filename="report.pdf",
            sha256_hash="aa" * 32,
            file_size=2048,
        ),
        make_file(
            source="macbook_local",
            source_path="/Users/test/report.pdf",
            filename="report.pdf",
            sha256_hash="aa" * 32,
            file_size=2048,
        ),
        make_file(
            source="macbook_local",
            source_path="/Users/test/other.pdf",
            filename="other.pdf",
            sha256_hash="bb" * 32,
            file_size=512,
        ),
    ]
    for rec in records:
        insert_file(manifest_conn, rec)
    return manifest_conn, records


@pytest.fixture
def temp_creds_dir():
    """Temporary credentials directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "credentials"
        path.mkdir()
        (path / "encrypted").mkdir()
        yield path


@pytest.fixture
def temp_db():
    """Temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name


@pytest.fixture
def mock_onedrive_api():
    """Mock OneDrive API responses."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"id": "file_123"}
    return mock


@pytest.fixture
def mock_google_api():
    """Mock Google Drive API responses."""
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"id": "file_456"}
    return mock
