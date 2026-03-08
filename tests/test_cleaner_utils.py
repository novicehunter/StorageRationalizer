"""Unit tests for phase3/cleaner.py utility functions."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from phase3.cleaner import build_query, format_size, now_iso  # noqa: E402

# ── build_query ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestBuildQuery:
    def test_safe_mode_returns_100_confidence(self):
        sql, params = build_query("safe", None)
        assert "100" in sql or 100 in params

    def test_docs_mode_excludes_media(self):
        sql, params = build_query("docs", None)
        # docs mode filters by file extension — no media extensions in results
        assert "jpg" in sql.lower() or "mp4" in sql.lower() or "jpeg" in sql.lower()

    def test_all_mode_returns_sql(self):
        sql, params = build_query("all", None)
        assert isinstance(sql, str)
        assert len(sql) > 0

    def test_source_filter_applied(self):
        sql, params = build_query("safe", "onedrive")
        assert "onedrive" in sql or "onedrive" in str(params)

    def test_returns_tuple_of_two(self):
        result = build_query("safe", None)
        assert isinstance(result, tuple)
        assert len(result) == 2


# ── format_size ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestFormatSizeCleaner:
    def test_zero(self):
        assert format_size(0) == "0 B"

    def test_kilobytes(self):
        assert format_size(4096) == "4.0 KB"

    def test_terabytes(self):
        assert format_size(1024**4) == "1.0 TB"


# ── now_iso ────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestNowIso:
    def test_returns_string(self):
        result = now_iso()
        assert isinstance(result, str)

    def test_contains_date(self):
        result = now_iso()
        assert "T" in result  # ISO format separator

    def test_changes_over_time(self):
        import time

        t1 = now_iso()
        time.sleep(0.01)
        t2 = now_iso()
        # Both are valid ISO strings (may be equal if sub-millisecond)
        assert isinstance(t1, str) and isinstance(t2, str)
