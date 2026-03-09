"""Integration tests for manifest DB operations (in-memory SQLite)."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from tests.conftest import insert_file, make_file  # noqa: E402


@pytest.mark.integration
class TestManifestDB:
    def test_insert_and_retrieve(self, manifest_conn):
        rec = make_file(source="macbook_local", filename="hello.pdf")
        insert_file(manifest_conn, rec)
        row = manifest_conn.execute(
            "SELECT * FROM files WHERE file_id=?", (rec["file_id"],)
        ).fetchone()
        assert row is not None
        assert row["filename"] == "hello.pdf"
        assert row["source"] == "macbook_local"

    def test_duplicate_insert_replaces(self, manifest_conn):
        rec = make_file(source="macbook_local", filename="dup.pdf")
        insert_file(manifest_conn, rec)
        rec["filename"] = "dup_updated.pdf"
        insert_file(manifest_conn, rec)
        count = manifest_conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert count == 1

    def test_multiple_sources(self, sample_files):
        conn, records = sample_files
        count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        assert count == 4

    def test_hash_lookup(self, sample_files):
        conn, records = sample_files
        rows = conn.execute("SELECT * FROM files WHERE sha256_hash=?", ("aa" * 32,)).fetchall()
        assert len(rows) == 3  # google_drive, onedrive, macbook_local

    def test_source_filter(self, sample_files):
        conn, _ = sample_files
        rows = conn.execute("SELECT * FROM files WHERE source='macbook_local'").fetchall()
        assert len(rows) == 2

    def test_google_drive_not_deleted_query(self, sample_files):
        """Sanity check: a query excluding google_drive source works."""
        conn, _ = sample_files
        rows = conn.execute("SELECT * FROM files WHERE source != 'google_drive'").fetchall()
        sources = {r["source"] for r in rows}
        assert "google_drive" not in sources
