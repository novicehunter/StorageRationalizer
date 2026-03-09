"""
Integration tests for CredentialsManager (AES-256-GCM encrypted storage).

Tests the full save → load → verify cycle, encryption on disk,
key rotation, missing key/service handling, and cache eviction.
Uses a temporary directory so no real credentials are touched.
"""

import json
import threading
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from tools.credentials_manager import CredentialsManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def creds_dir():
    """Isolated temporary credentials directory for each test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        d = Path(tmpdir) / "encrypted"
        d.mkdir()
        yield d


@pytest.fixture
def cm(creds_dir):
    """CredentialsManager pointed at the temp dir, with password pre-injected."""
    manager = CredentialsManager(encrypted_dir=creds_dir)
    # Inject password directly into cache to avoid interactive getpass prompt
    manager._cached_password = "test-master-password"  # pragma: allowlist secret
    manager._cache_ts = float("inf")  # Never expire during tests
    return manager


# ---------------------------------------------------------------------------
# Save / Load cycle
# ---------------------------------------------------------------------------


class TestSaveLoadCycle:
    def test_save_and_load_returns_original_value(self, cm):
        cm.save("svc", "api_key", "secret-value-abc")
        assert cm.load("svc", "api_key") == "secret-value-abc"

    def test_save_multiple_keys_same_service(self, cm):
        cm.save("google", "client_id", "id-123")
        cm.save("google", "client_secret", "secret-456")
        assert cm.load("google", "client_id") == "id-123"
        assert cm.load("google", "client_secret") == "secret-456"

    def test_save_multiple_services_isolated(self, cm):
        cm.save("google", "token", "google-token")
        cm.save("onedrive", "token", "onedrive-token")
        assert cm.load("google", "token") == "google-token"
        assert cm.load("onedrive", "token") == "onedrive-token"

    def test_overwrite_existing_key(self, cm):
        cm.save("svc", "key", "old-value")
        cm.save("svc", "key", "new-value")
        assert cm.load("svc", "key") == "new-value"

    def test_unicode_value_preserved(self, cm):
        cm.save("svc", "key", "value-with-unicode-\u4e2d\u6587-\U0001f600")
        assert cm.load("svc", "key") == "value-with-unicode-\u4e2d\u6587-\U0001f600"

    def test_empty_string_value_preserved(self, cm):
        cm.save("svc", "key", "")
        assert cm.load("svc", "key") == ""

    def test_long_value_preserved(self, cm):
        long_value = "x" * 10_000
        cm.save("svc", "long", long_value)
        assert cm.load("svc", "long") == long_value


# ---------------------------------------------------------------------------
# Encryption on disk
# ---------------------------------------------------------------------------


class TestEncryptionOnDisk:
    def test_enc_file_created(self, cm, creds_dir):
        cm.save("svc", "key", "secret")
        assert (creds_dir / "svc.enc").exists()

    def test_meta_file_created(self, cm, creds_dir):
        cm.save("svc", "key", "secret")
        assert (creds_dir / "svc.meta").exists()

    def test_plaintext_not_in_enc_file(self, cm, creds_dir):
        cm.save("svc", "key", "super-secret-value")
        raw = (creds_dir / "svc.enc").read_bytes()
        assert b"super-secret-value" not in raw

    def test_key_name_not_in_enc_file(self, cm, creds_dir):
        cm.save("svc", "api_key", "secret")
        raw = (creds_dir / "svc.enc").read_bytes()
        assert b"api_key" not in raw

    def test_meta_contains_salt_and_iv(self, cm, creds_dir):
        cm.save("svc", "key", "value")
        meta = json.loads((creds_dir / "svc.meta").read_text())
        assert "salt" in meta
        assert "iv" in meta
        # salt and iv should be hex strings of the right length (32 and 12 bytes)
        assert len(bytes.fromhex(meta["salt"])) == 32
        assert len(bytes.fromhex(meta["iv"])) == 12

    def test_different_encryptions_produce_different_ciphertext(self, cm, creds_dir):
        """Each save should use a fresh random salt/IV."""
        cm.save("svc", "key", "same-value")
        ct1 = (creds_dir / "svc.enc").read_bytes()

        # Save again to force re-encryption
        cm.save("svc", "key2", "same-value")
        ct2 = (creds_dir / "svc.enc").read_bytes()

        # Ciphertexts should differ (different salt/IV)
        assert ct1 != ct2


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_load_missing_service_raises_file_not_found(self, cm):
        with pytest.raises(FileNotFoundError):
            cm.load("nonexistent_service", "key")

    def test_load_missing_key_raises_key_error(self, cm):
        cm.save("svc", "existing_key", "value")
        with pytest.raises(KeyError):
            cm.load("svc", "missing_key")

    def test_wrong_password_raises_runtime_error(self, creds_dir):
        writer = CredentialsManager(encrypted_dir=creds_dir)
        writer._cached_password = "correct-password"  # pragma: allowlist secret
        writer._cache_ts = float("inf")
        writer.save("svc", "key", "value")

        reader = CredentialsManager(encrypted_dir=creds_dir)
        reader._cached_password = "wrong-password"  # pragma: allowlist secret
        reader._cache_ts = float("inf")

        with pytest.raises(RuntimeError, match="Failed to decrypt"):
            reader.load("svc", "key")


# ---------------------------------------------------------------------------
# Credential rotation
# ---------------------------------------------------------------------------


class TestCredentialRotation:
    def test_rotate_by_overwriting_key(self, cm):
        cm.save("svc", "token", "old-token")
        assert cm.load("svc", "token") == "old-token"

        cm.save("svc", "token", "new-token")
        assert cm.load("svc", "token") == "new-token"

    def test_other_keys_unaffected_by_rotation(self, cm):
        cm.save("svc", "token", "old-token")
        cm.save("svc", "other", "other-value")
        cm.save("svc", "token", "new-token")

        assert cm.load("svc", "token") == "new-token"
        assert cm.load("svc", "other") == "other-value"


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


class TestCacheManagement:
    def test_clear_cache_evicts_password(self, cm):
        cm.clear_cache()
        assert cm._cached_password is None
        assert cm._cache_ts == 0.0

    def test_after_cache_clear_password_reprompted(self, cm):
        cm.save("svc", "key", "value")
        cm.clear_cache()

        # After clear, next load should prompt for password
        with patch(
            "tools.credentials_manager.getpass.getpass", return_value="test-master-password"
        ):
            result = cm.load("svc", "key")
        assert result == "value"


# ---------------------------------------------------------------------------
# Concurrency (basic thread safety smoke test)
# ---------------------------------------------------------------------------


class TestConcurrency:
    def test_concurrent_saves_to_different_services(self, creds_dir):
        """Multiple threads saving to different services should not interfere."""
        errors = []

        def save_cred(service_index):
            manager = CredentialsManager(encrypted_dir=creds_dir)
            manager._cached_password = "test-master-password"  # pragma: allowlist secret
            manager._cache_ts = float("inf")
            try:
                manager.save(f"svc_{service_index}", "key", f"value_{service_index}")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=save_cred, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Errors during concurrent saves: {errors}"

    def test_concurrent_reads_return_correct_values(self, creds_dir):
        """Multiple readers on different services should get correct values."""
        # Setup
        for i in range(8):
            manager = CredentialsManager(encrypted_dir=creds_dir)
            manager._cached_password = "test-master-password"  # pragma: allowlist secret
            manager._cache_ts = float("inf")
            manager.save(f"svc_{i}", "key", f"value_{i}")

        results = {}
        errors = []

        def read_cred(service_index):
            manager = CredentialsManager(encrypted_dir=creds_dir)
            manager._cached_password = "test-master-password"  # pragma: allowlist secret
            manager._cache_ts = float("inf")
            try:
                val = manager.load(f"svc_{service_index}", "key")
                results[service_index] = val
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_cred, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Errors during concurrent reads: {errors}"
        for i in range(8):
            assert results[i] == f"value_{i}"
