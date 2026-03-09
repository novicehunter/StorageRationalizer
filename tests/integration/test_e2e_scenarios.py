"""
End-to-end integration tests combining all three security modules.

Simulates real-world restore workflows: credentials → API validation →
file path validation → AppleScript generation. Uses mocks for password
prompts and HTTP responses so tests run without real cloud accounts.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tools.api_validators import APIResponseError, validate_restore_response
from tools.credentials_manager import CredentialsManager
from tools.input_validators import (
    InputValidationError,
    build_safe_applescript_put_back,
    validate_file_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def creds_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        d = Path(tmpdir) / "encrypted"
        d.mkdir()
        yield d


@pytest.fixture
def cm(creds_dir):
    manager = CredentialsManager(encrypted_dir=creds_dir)
    manager._cached_password = "test-password"  # pragma: allowlist secret
    manager._cache_ts = float("inf")
    return manager


@pytest.fixture
def real_file(tmp_path):
    f = tmp_path / "restored_document.pdf"
    f.write_text("file content here")
    return f


@pytest.fixture
def dest_dir(tmp_path):
    d = tmp_path / "destination"
    d.mkdir()
    return d


def make_response(status_code, json_body):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_body
    mock.text = str(json_body)
    return mock


# ---------------------------------------------------------------------------
# E2E: Successful restore flow
# ---------------------------------------------------------------------------


class TestSuccessfulRestoreFlow:
    def test_load_credential_and_validate_api_response(self, cm):
        """Simulate: load stored token → validate API response with it."""
        cm.save("onedrive", "access_token", "Bearer eyJtest123")

        token = cm.load("onedrive", "access_token")
        assert token.startswith("Bearer")

        resp = make_response(200, {"id": "file_001", "name": "report.pdf"})
        data = validate_restore_response(resp, expected_file_id="file_001")
        assert data["id"] == "file_001"

    def test_validate_path_then_build_script(self, real_file, dest_dir):
        """Simulate: validate restored file path → build AppleScript."""
        validated = validate_file_path(str(real_file))
        script = build_safe_applescript_put_back(validated, str(dest_dir))

        assert "Finder" in script
        assert "move" in script
        assert real_file.name in script

    def test_full_pipeline_cred_api_path_script(self, cm, real_file, dest_dir):
        """Full pipeline: load cred → validate API → validate path → build script."""
        # 1. Load credential
        cm.save("onedrive", "token", "test-token")
        token = cm.load("onedrive", "token")
        assert token == "test-token"

        # 2. Validate API response (simulated with token)
        resp = make_response(200, {"id": "file_xyz", "name": real_file.name})
        data = validate_restore_response(resp, expected_file_id="file_xyz")
        assert data["id"] == "file_xyz"

        # 3. Validate restored file path
        safe_path = validate_file_path(str(real_file))

        # 4. Build AppleScript
        script = build_safe_applescript_put_back(safe_path, str(dest_dir))
        assert real_file.name in script

    def test_multiple_files_batch_restore(self, cm, tmp_path):
        """Simulate restoring multiple files with batch API response."""
        dest = tmp_path / "dest"
        dest.mkdir()

        # Create 3 files
        files = []
        for i in range(3):
            f = tmp_path / f"file_{i}.pdf"
            f.write_text(f"content {i}")
            files.append(f)

        # Validate all paths
        safe_paths = [validate_file_path(str(f)) for f in files]
        assert len(safe_paths) == 3

        # Build scripts for each
        scripts = [build_safe_applescript_put_back(p, str(dest)) for p in safe_paths]
        assert all("Finder" in s for s in scripts)


# ---------------------------------------------------------------------------
# E2E: Failure handling
# ---------------------------------------------------------------------------


class TestFailureHandling:
    def test_missing_credential_blocks_restore(self, cm):
        """If credential is missing, the pipeline should fail before API call."""
        with pytest.raises(Exception):  # FileNotFoundError from CredentialsManager
            cm.load("onedrive", "nonexistent_token")

    def test_api_error_blocks_file_operation(self, real_file, dest_dir):
        """If API returns an error, file operations should not proceed."""
        resp = make_response(404, {"error": {"code": "itemNotFound", "message": "Not found"}})

        with pytest.raises(APIResponseError):
            validate_restore_response(resp, expected_file_id="file_001")

        # File operation never reached — no assertion needed, test passes if above raises

    def test_invalid_file_path_blocks_script_generation(self, tmp_path, dest_dir):
        """If the file doesn't exist, script generation should be blocked."""
        missing_file = tmp_path / "ghost.pdf"
        with pytest.raises(InputValidationError, match="does not exist"):
            validate_file_path(str(missing_file))

    def test_symlink_path_blocks_restore(self, real_file, dest_dir, tmp_path):
        """Symlinks in the restored path should be rejected."""
        link = tmp_path / "sneaky_link.pdf"
        link.symlink_to(real_file)

        with pytest.raises(InputValidationError, match="symlink"):
            build_safe_applescript_put_back(str(link), str(dest_dir))

    def test_api_id_mismatch_blocks_restore(self):
        """If API returns a different file ID, the restore should be rejected."""
        resp = make_response(200, {"id": "different_file_id"})
        with pytest.raises(APIResponseError, match="mismatch"):
            validate_restore_response(resp, expected_file_id="expected_file_id")

    def test_credential_wrong_password_blocks_pipeline(self, creds_dir):
        """Wrong master password should prevent credential loading."""
        writer = CredentialsManager(encrypted_dir=creds_dir)
        writer._cached_password = "correct-password"  # pragma: allowlist secret
        writer._cache_ts = float("inf")
        writer.save("svc", "token", "secret")

        reader = CredentialsManager(encrypted_dir=creds_dir)
        reader._cached_password = "wrong-password"  # pragma: allowlist secret
        reader._cache_ts = float("inf")

        with pytest.raises(RuntimeError, match="Failed to decrypt"):
            reader.load("svc", "token")


# ---------------------------------------------------------------------------
# E2E: Credential rotation during operation
# ---------------------------------------------------------------------------


class TestCredentialRotation:
    def test_rotate_token_and_continue_restores(self, cm, real_file, dest_dir):
        """After rotating a token, subsequent operations use the new value."""
        cm.save("onedrive", "token", "old-token-v1")
        assert cm.load("onedrive", "token") == "old-token-v1"

        # Rotate
        cm.save("onedrive", "token", "new-token-v2")
        assert cm.load("onedrive", "token") == "new-token-v2"

        # Continue with new token — validate API response
        resp = make_response(200, {"id": "file_abc"})
        data = validate_restore_response(resp, expected_file_id="file_abc")
        assert data["id"] == "file_abc"

    def test_multiple_services_rotate_independently(self, cm):
        """Rotating one service's credentials does not affect others."""
        cm.save("google", "token", "google-v1")
        cm.save("onedrive", "token", "onedrive-v1")

        cm.save("onedrive", "token", "onedrive-v2")

        assert cm.load("google", "token") == "google-v1"
        assert cm.load("onedrive", "token") == "onedrive-v2"
