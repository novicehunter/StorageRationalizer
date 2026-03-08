"""Unit tests for phase2/classifier.py logic."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from phase2.classifier import format_size, make_group_id, pick_keeper  # noqa: E402
from tests.conftest import make_file  # noqa: E402

# ── pick_keeper ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestPickKeeper:
    def test_google_drive_wins_over_onedrive(self):
        members = [
            make_file(source="onedrive"),
            make_file(source="google_drive"),
        ]
        keeper = pick_keeper(members)
        assert keeper["source"] == "google_drive"

    def test_onedrive_wins_over_macbook(self):
        members = [
            make_file(source="macbook_local"),
            make_file(source="onedrive"),
        ]
        keeper = pick_keeper(members)
        assert keeper["source"] == "onedrive"

    def test_macbook_wins_over_icloud_drive(self):
        members = [
            make_file(source="icloud_drive"),
            make_file(source="macbook_local"),
        ]
        keeper = pick_keeper(members)
        assert keeper["source"] == "macbook_local"

    def test_icloud_drive_wins_over_icloud_photos(self):
        members = [
            make_file(source="icloud_photos"),
            make_file(source="icloud_drive"),
        ]
        keeper = pick_keeper(members)
        assert keeper["source"] == "icloud_drive"

    def test_full_priority_chain(self):
        members = [
            make_file(source="icloud_photos"),
            make_file(source="icloud_drive"),
            make_file(source="macbook_local"),
            make_file(source="onedrive"),
            make_file(source="google_drive"),
        ]
        keeper = pick_keeper(members)
        assert keeper["source"] == "google_drive"

    def test_size_tiebreak_prefers_larger(self):
        members = [
            make_file(source="macbook_local", file_size=1000),
            make_file(source="macbook_local", file_size=5000),
        ]
        keeper = pick_keeper(members)
        assert keeper["file_size"] == 5000

    def test_single_member_returned(self):
        members = [make_file(source="onedrive")]
        keeper = pick_keeper(members)
        assert keeper["source"] == "onedrive"


# ── make_group_id ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestMakeGroupId:
    def test_deterministic(self):
        gid1 = make_group_id("exact_hash", "abc123")
        gid2 = make_group_id("exact_hash", "abc123")
        assert gid1 == gid2

    def test_different_keys_differ(self):
        gid1 = make_group_id("exact_hash", "abc")
        gid2 = make_group_id("exact_hash", "xyz")
        assert gid1 != gid2

    def test_different_types_differ(self):
        gid1 = make_group_id("exact_hash", "key")
        gid2 = make_group_id("cross_source", "key")
        assert gid1 != gid2

    def test_returns_hex_string(self):
        gid = make_group_id("exact_hash", "test")
        assert len(gid) == 32
        assert all(c in "0123456789abcdef" for c in gid)


# ── format_size (classifier's copy) ───────────────────────────────────────────


@pytest.mark.unit
class TestFormatSizeClassifier:
    def test_zero(self):
        assert format_size(0) == "0 B"

    def test_megabytes(self):
        assert format_size(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self):
        assert format_size(1024**3) == "1.0 GB"
