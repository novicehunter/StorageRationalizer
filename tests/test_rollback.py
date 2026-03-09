"""
Stub tests for tools/rollback.py — RollbackManager.

Status: STUB — 10 placeholder tests to be implemented in Phase 4.
These tests define the expected behaviour of the rollback module;
implementations are marked with pytest.skip until real test data
(rollback.db, cleanup_*.log) is available.

See: docs/EXTENDED_TESTING_PLAN.md
"""

import sqlite3

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rollback_db(tmp_path):
    """Minimal in-memory rollback DB matching rollback.py schema."""
    db_path = tmp_path / "rollback.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deleted_files (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id        TEXT NOT NULL,
            source        TEXT NOT NULL,
            cloud_file_id TEXT,
            local_path    TEXT,
            filename      TEXT NOT NULL,
            file_size     INTEGER,
            trash_path    TEXT,
            deleted_at    TEXT NOT NULL,
            restored_at   TEXT,
            status        TEXT DEFAULT 'deleted'
        )
    """
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def sample_log(tmp_path):
    """Minimal cleanup log file for parsing tests."""
    log_content = (
        "[2026-03-08T15:50:28+00:00] TRASHED onedrive FE7C8667ED2A37CF!112 report.pdf\n"
        "[2026-03-08T15:51:00+00:00] DELETED local /Users/test/old.txt\n"
        "[2026-03-08T15:52:00+00:00] TRASHED google_drive abc123def report2.pdf\n"
    )
    log_path = tmp_path / "cleanup_20260308_155028.log"
    log_path.write_text(log_content)
    return log_path


# ---------------------------------------------------------------------------
# Stub tests — to be implemented
# ---------------------------------------------------------------------------


class TestRollbackDBSetup:
    @pytest.mark.skip(reason="STUB: implement after rollback.db schema confirmed")
    def test_rollback_db_creates_schema(self, tmp_path):
        """rollback.py --sync should create rollback.db with correct schema."""
        pass

    @pytest.mark.skip(reason="STUB: implement after rollback.db schema confirmed")
    def test_rollback_db_idempotent(self, tmp_path):
        """Running --sync twice should not duplicate records."""
        pass


class TestLogParsing:
    @pytest.mark.skip(reason="STUB: implement once parse_log_entries is importable")
    def test_parse_onedrive_trashed_entry(self, sample_log):
        """TRASHED onedrive entries should be parsed with cloud_file_id."""
        pass

    @pytest.mark.skip(reason="STUB: implement once parse_log_entries is importable")
    def test_parse_local_deleted_entry(self, sample_log):
        """DELETED local entries should be parsed with local_path."""
        pass

    @pytest.mark.skip(reason="STUB: implement once parse_log_entries is importable")
    def test_parse_google_drive_trashed_entry(self, sample_log):
        """TRASHED google_drive entries should be parsed with cloud_file_id."""
        pass

    @pytest.mark.skip(reason="STUB: implement once parse_log_entries is importable")
    def test_empty_log_returns_no_entries(self, tmp_path):
        """Empty log file should return empty list."""
        pass


class TestRestoreOperations:
    @pytest.mark.skip(reason="STUB: requires rollback.db with real data and macOS Trash")
    def test_restore_local_file_from_trash(self, rollback_db, tmp_path):
        """Local files should be moved from .Trash back to original path."""
        pass

    @pytest.mark.skip(reason="STUB: requires OneDrive API credentials")
    def test_restore_onedrive_file(self, rollback_db):
        """OneDrive files should be restored via Microsoft Graph API."""
        pass

    @pytest.mark.skip(reason="STUB: requires full run_id in rollback.db")
    def test_restore_by_run_id_scope(self, rollback_db):
        """--scope run should restore all files from the given run_id."""
        pass

    @pytest.mark.skip(reason="STUB: requires populated rollback.db")
    def test_restore_by_file_ids(self, rollback_db):
        """--file-ids 1,2,3 should restore exactly those records."""
        pass
