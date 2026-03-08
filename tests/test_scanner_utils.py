"""Unit tests for phase1/scanner.py utility functions."""

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from phase1.scanner import (  # noqa: E402
    categorize,
    format_size,
    safe_iso,
    sha256_file,
    should_skip,
)

# ── categorize ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestCategorize:
    def test_photo_extension(self):
        assert categorize(".jpg") == (1, 0, 0)

    def test_video_extension(self):
        assert categorize(".mp4") == (0, 1, 0)

    def test_document_extension(self):
        assert categorize(".pdf") == (0, 0, 1)

    def test_unknown_extension(self):
        assert categorize(".xyz") == (0, 0, 0)

    def test_case_insensitive(self):
        assert categorize(".JPG") == (1, 0, 0)
        assert categorize(".MP4") == (0, 1, 0)

    def test_heic_is_photo(self):
        assert categorize(".heic") == (1, 0, 0)

    def test_docx_is_document(self):
        assert categorize(".docx") == (0, 0, 1)


# ── should_skip ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestShouldSkip:
    def test_skip_git_dir(self):
        assert should_skip(Path("/home/user/.git/config"))

    def test_skip_node_modules(self):
        assert should_skip(Path("/project/node_modules/lib/index.js"))

    def test_skip_tmp_file(self):
        assert should_skip(Path("/some/dir/work.tmp"))

    def test_normal_file_not_skipped(self):
        assert not should_skip(Path("/home/user/Documents/report.pdf"))

    def test_pycache_skipped(self):
        assert should_skip(Path("/project/__pycache__/module.pyc"))


# ── format_size ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestFormatSize:
    def test_zero(self):
        assert format_size(0) == "0 B"

    def test_none(self):
        assert format_size(None) == "0 B"

    def test_bytes(self):
        assert format_size(512) == "512.0 B"

    def test_kilobytes(self):
        assert format_size(2048) == "2.0 KB"

    def test_megabytes(self):
        assert format_size(5 * 1024 * 1024) == "5.0 MB"

    def test_gigabytes(self):
        assert format_size(2 * 1024**3) == "2.0 GB"


# ── sha256_file ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSha256File:
    def test_known_hash(self, tmp_path):
        data = b"hello world"
        f = tmp_path / "test.txt"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert sha256_file(f) == expected

    def test_missing_file_returns_none(self, tmp_path):
        result = sha256_file(tmp_path / "nonexistent.txt")
        assert result is None

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.bin"
        f.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert sha256_file(f) == expected


# ── safe_iso ───────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSafeIso:
    def test_none_returns_none(self):
        assert safe_iso(None) is None

    def test_string_passthrough(self):
        s = "2024-01-01T00:00:00+00:00"
        assert safe_iso(s) == s

    def test_aware_datetime(self):
        dt = datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = safe_iso(dt)
        assert "2024-06-01" in result

    def test_naive_datetime_gets_utc(self):
        dt = datetime(2024, 6, 1, 12, 0, 0)
        result = safe_iso(dt)
        assert result is not None
        assert "2024-06-01" in result
