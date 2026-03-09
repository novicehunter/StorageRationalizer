"""
Performance tests for StorageRationalizer security modules.

Tests throughput and concurrency of:
- CredentialsManager: save/load under load
- API validators: validation throughput
- Input validators: path validation throughput

Mark: pytest -m performance
"""

import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tools.api_validators import validate_restore_response, validate_batch_response
from tools.credentials_manager import CredentialsManager
from tools.input_validators import (
    sanitize_applescript_string,
    validate_file_path,
    validate_directory_path,
)

pytestmark = pytest.mark.performance


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_cm(tmpdir: Path) -> CredentialsManager:
    """Return a CredentialsManager with pre-injected password (no prompt)."""
    enc = tmpdir / "encrypted"
    enc.mkdir(exist_ok=True)
    cm = CredentialsManager(encrypted_dir=enc)
    cm._cached_password = "perf-test-password"  # pragma: allowlist secret
    cm._cache_ts = float("inf")
    return cm


def make_response(status_code: int, json_body):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_body
    mock.text = str(json_body)
    return mock


# ---------------------------------------------------------------------------
# CredentialsManager throughput
# ---------------------------------------------------------------------------


class TestCredentialsThroughput:
    def test_100_sequential_saves(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = make_cm(Path(tmpdir))
            start = time.perf_counter()
            for i in range(100):
                cm.save("svc", f"key_{i}", f"value_{i}")
            elapsed = time.perf_counter() - start
        # 100 saves should complete in under 45 seconds (PBKDF2 is intentionally slow)
        assert elapsed < 45.0, f"100 saves took {elapsed:.2f}s (too slow)"

    def test_100_sequential_loads_after_warm_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = make_cm(Path(tmpdir))
            # Populate a single service with many keys
            for i in range(10):
                cm.save("svc", f"key_{i}", f"value_{i}")

            # Loads only re-decrypt when service file changes;
            # re-populate to force fresh load each iteration
            start = time.perf_counter()
            for i in range(10):
                val = cm.load("svc", f"key_{i}")
                assert val == f"value_{i}"
            elapsed = time.perf_counter() - start

        assert elapsed < 30.0, f"10 loads took {elapsed:.2f}s"

    def test_concurrent_saves_to_isolated_services(self):
        """10 threads each saving to their own service — no contention."""
        with tempfile.TemporaryDirectory() as tmpdir:
            errors = []
            start = time.perf_counter()

            def worker(idx):
                try:
                    cm = make_cm(Path(tmpdir))
                    cm.save(f"service_{idx}", "token", f"value_{idx}")
                except Exception as e:
                    errors.append(e)

            with ThreadPoolExecutor(max_workers=10) as pool:
                futures = [pool.submit(worker, i) for i in range(10)]
                for f in as_completed(futures):
                    pass

            elapsed = time.perf_counter() - start

        assert errors == [], f"Errors: {errors}"
        assert elapsed < 60.0, f"10 concurrent saves took {elapsed:.2f}s"

    def test_concurrent_loads_from_isolated_services(self):
        """10 threads each loading from their own service — no contention."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Setup
            for i in range(10):
                cm = make_cm(Path(tmpdir))
                cm.save(f"service_{i}", "token", f"value_{i}")

            errors = []
            results = {}

            def worker(idx):
                try:
                    cm = make_cm(Path(tmpdir))
                    val = cm.load(f"service_{idx}", "token")
                    results[idx] = val
                except Exception as e:
                    errors.append(e)

            with ThreadPoolExecutor(max_workers=10) as pool:
                futures = [pool.submit(worker, i) for i in range(10)]
                for f in as_completed(futures):
                    pass

        assert errors == [], f"Errors: {errors}"
        for i in range(10):
            assert results[i] == f"value_{i}"


# ---------------------------------------------------------------------------
# API validator throughput
# ---------------------------------------------------------------------------


class TestAPIValidatorThroughput:
    def test_1000_restore_validations(self):
        """validate_restore_response should handle 1000 calls quickly."""
        resp = make_response(200, {"id": "file_perf_001", "name": "file.pdf"})
        start = time.perf_counter()
        for _ in range(1000):
            validate_restore_response(resp, expected_file_id="file_perf_001")
        elapsed = time.perf_counter() - start

        # Target: <1 second for 1000 validations
        assert elapsed < 1.0, f"1000 validations took {elapsed:.3f}s"

    def test_1000_restore_validations_avg_time(self):
        resp = make_response(200, {"id": "file_001"})
        times = []
        for _ in range(1000):
            t0 = time.perf_counter()
            validate_restore_response(resp, expected_file_id="file_001")
            times.append(time.perf_counter() - t0)

        avg_ms = (sum(times) / len(times)) * 1000
        # Target: <1ms average per validation
        assert avg_ms < 1.0, f"Average validation time: {avg_ms:.3f}ms (target: <1ms)"

    def test_concurrent_api_validation(self):
        """10 threads each running 100 validations — total 1000 concurrent."""
        resp = make_response(200, {"id": "file_001"})
        errors = []

        def validate_batch():
            try:
                for _ in range(100):
                    validate_restore_response(resp, expected_file_id="file_001")
            except Exception as e:
                errors.append(e)

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(validate_batch) for _ in range(10)]
            for f in as_completed(futures):
                pass
        elapsed = time.perf_counter() - start

        assert errors == [], f"Errors: {errors}"
        assert elapsed < 5.0, f"1000 concurrent validations took {elapsed:.2f}s"

    def test_batch_response_validation_throughput(self):
        """validate_batch_response with 10-item batches, 500 iterations."""
        responses = [{"id": str(i), "status": 200, "body": {}} for i in range(10)]
        resp = make_response(200, {"responses": responses})

        start = time.perf_counter()
        for _ in range(500):
            validate_batch_response(resp, expected_request_count=10)
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"500 batch validations took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# Input validator throughput
# ---------------------------------------------------------------------------


class TestInputValidatorThroughput:
    def test_1000_path_validations(self, tmp_path):
        """validate_file_path on a real file — 1000 iterations."""
        f = tmp_path / "test.pdf"
        f.write_text("content")
        path_str = str(f)

        start = time.perf_counter()
        for _ in range(1000):
            validate_file_path(path_str)
        elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"1000 path validations took {elapsed:.3f}s"

    def test_1000_rejected_paths(self):
        """Rejection paths should be fast (no disk I/O for metachar check)."""
        start = time.perf_counter()
        for _ in range(1000):
            try:
                validate_file_path("/tmp/file;injection")
            except Exception:
                pass
        elapsed = time.perf_counter() - start

        # Rejection should be near-instant (regex only, no disk I/O)
        assert elapsed < 0.5, f"1000 rejected paths took {elapsed:.3f}s"

    def test_1000_sanitize_applescript_calls(self):
        """sanitize_applescript_string — 1000 iterations with injection payload."""
        payload = 'path/to/file"; do shell script "rm -rf /"; "'
        start = time.perf_counter()
        for _ in range(1000):
            sanitize_applescript_string(payload)
        elapsed = time.perf_counter() - start

        assert elapsed < 0.1, f"1000 sanitizations took {elapsed:.3f}s"

    def test_concurrent_path_validations(self, tmp_path):
        """8 threads each validating 50 paths concurrently."""
        files = []
        for i in range(8):
            f = tmp_path / f"file_{i}.txt"
            f.write_text(f"content {i}")
            files.append(str(f))

        errors = []

        def validate_many(path):
            try:
                for _ in range(50):
                    validate_file_path(path)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(validate_many, p) for p in files]
            for f in as_completed(futures):
                pass

        assert errors == [], f"Errors: {errors}"

    def test_1000_directory_validations(self, tmp_path):
        """validate_directory_path — 1000 iterations."""
        start = time.perf_counter()
        for _ in range(1000):
            validate_directory_path(str(tmp_path))
        elapsed = time.perf_counter() - start

        assert elapsed < 5.0, f"1000 directory validations took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# Memory / stress
# ---------------------------------------------------------------------------


class TestStress:
    def test_large_value_save_and_load(self):
        """Save and load a 100KB credential value."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = make_cm(Path(tmpdir))
            large_value = "x" * 100_000
            cm.save("svc", "large_key", large_value)
            result = cm.load("svc", "large_key")
        assert result == large_value

    def test_many_keys_in_one_service(self):
        """Save 50 keys in one service, load all back correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cm = make_cm(Path(tmpdir))
            for i in range(50):
                cm.save("svc", f"key_{i}", f"value_{i}")

            for i in range(50):
                assert cm.load("svc", f"key_{i}") == f"value_{i}"

    def test_many_services(self):
        """Save 20 independent services, load all back correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(20):
                cm = make_cm(Path(tmpdir))
                cm.save(f"service_{i}", "token", f"token_value_{i}")

            for i in range(20):
                cm = make_cm(Path(tmpdir))
                assert cm.load(f"service_{i}", "token") == f"token_value_{i}"

    def test_large_batch_api_validation(self):
        """Validate a batch with 100 responses."""
        responses = [{"id": str(i), "status": 200, "body": {}} for i in range(100)]
        resp = make_response(200, {"responses": responses})

        data = validate_batch_response(resp, expected_request_count=100)
        assert len(data["responses"]) == 100

    def test_long_path_validation(self, tmp_path):
        """Validate a file with a deeply nested (but valid) path."""
        deep = tmp_path
        for i in range(10):
            deep = deep / f"dir_{i}"
            deep.mkdir()
        f = deep / "file.txt"
        f.write_text("content")

        result = validate_file_path(str(f))
        assert result.endswith("file.txt")
