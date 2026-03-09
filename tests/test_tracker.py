"""
Stub tests for tools/tracker.py — Flask progress tracker UI.

Status: STUB — 10 placeholder tests to be implemented in Phase 4.
Uses Flask test client to avoid starting a real server.

See: docs/EXTENDED_TESTING_PLAN.md
"""

import pytest

# ---------------------------------------------------------------------------
# Flask test client fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client with temporary SQLite DB."""
    pytest.importorskip("flask")

    # Point the tracker DB at a temp path before importing
    monkeypatch.setenv("TRACKER_DB", str(tmp_path / "tracker_test.db"))

    # Importing tracker.py starts Flask app setup
    # Note: tracker.py also imports rollback — both modules must be importable
    try:
        import tools.tracker as tracker  # noqa: F401

        tracker.app.config["TESTING"] = True
        tracker.app.config["DATABASE"] = str(tmp_path / "tracker_test.db")
        with tracker.app.test_client() as c:
            yield c
    except Exception:
        pytest.skip(
            "tracker.py not importable in this environment (missing Flask or rollback deps)"
        )


# ---------------------------------------------------------------------------
# Stub tests — to be implemented
# ---------------------------------------------------------------------------


class TestTrackerRoutes:
    @pytest.mark.skip(reason="STUB: implement once Flask routes are confirmed")
    def test_index_returns_200(self, client):
        """GET / should return HTTP 200."""
        pass

    @pytest.mark.skip(reason="STUB: implement once Flask routes are confirmed")
    def test_status_endpoint_returns_json(self, client):
        """GET /api/status should return JSON with storage stats."""
        pass

    @pytest.mark.skip(reason="STUB: implement once Flask routes are confirmed")
    def test_update_field_persists_to_db(self, client):
        """POST /api/update should persist field value to tracker_data.db."""
        pass

    @pytest.mark.skip(reason="STUB: implement once Flask routes are confirmed")
    def test_notes_endpoint_saves_content(self, client):
        """POST /api/notes should save section content."""
        pass

    @pytest.mark.skip(reason="STUB: implement once Flask routes are confirmed")
    def test_checklist_toggle_persists(self, client):
        """POST /api/checklist should toggle checked state."""
        pass


class TestTrackerDatabase:
    @pytest.mark.skip(reason="STUB: implement once DB schema is confirmed")
    def test_init_db_creates_tables(self, tmp_path):
        """init_db() should create fields, notes, checklist tables."""
        pass

    @pytest.mark.skip(reason="STUB: implement once DB schema is confirmed")
    def test_init_db_idempotent(self, tmp_path):
        """Calling init_db() twice should not raise or duplicate tables."""
        pass

    @pytest.mark.skip(reason="STUB: implement once DB schema is confirmed")
    def test_get_db_returns_connection(self, tmp_path):
        """get_db() should return a valid sqlite3 connection."""
        pass


class TestTrackerConstants:
    @pytest.mark.skip(reason="STUB: confirm TARGET_GB value with user")
    def test_target_gb_is_set(self):
        """TARGET_GB should be a positive float."""
        pass

    @pytest.mark.skip(reason="STUB: confirm logs directory path")
    def test_logs_dir_path_is_correct(self):
        """LOGS_DIR should point to ../logs relative to tools/."""
        pass
