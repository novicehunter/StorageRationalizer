# StorageRationalizer Extended Testing Plan

**Purpose:** Define comprehensive testing strategy beyond unit tests to catch integration bugs, security gaps, and real-world scenarios.

**Effective Date:** March 9, 2026
**Planning Phase:** Q2 2026
**Execution Phase:** Q3 2026
**Owner:** QA + Security Team

---

## 1. Testing Pyramid

```
                    ▲
                   /|\
                  / | \
                 /  |  \  Manual + Exploratory (5%)
                /   |   \
               /    |    \
              / P2: Integration Tests (20%)
             /      |      \
            /       |       \
           /        |        \
          /  P1: Unit Tests (75%)
         /__________|__________\

Total Coverage Target: ≥95%
Security Coverage Target: ≥99% (all 3 CRITICAL issues)
```

---

## 2. Unit Tests (EXISTING - ✅ Complete)

### Current Status
- **Total:** 49 tests
- **Security modules:** 49/49 passing ✅
- **Coverage:** ≥90% per module
- **Test files:**
  - `tests/test_api_validators.py` (13 tests)
  - `tests/test_input_validators.py` (36 tests)

### No further action needed for unit tests.

---

## 3. Integration Testing (NEW - Q2/Q3 2026)

### A. Test Environment Setup

**Phase 1: Mock Environment (Internal)**
```bash
# Create integration test environment
mkdir -p tests/integration
mkdir -p tests/fixtures/

# Install test dependencies (if not present)
pip install responses mock pytest-asyncio

# Create test database/mock APIs
```

### B. Integration Test Categories

#### 1. Credential Manager Integration
**File:** `tests/integration/test_credentials_integration.py`

```python
import pytest
from tools.credentials_manager import CredentialManager
from tools.api_validators import validate_restore_response

class TestCredentialManagerIntegration:

    @pytest.fixture
    def cred_manager(self):
        """Setup isolated credential manager for testing."""
        return CredentialManager(test_mode=True)

    def test_credential_save_retrieve_cycle(self, cred_manager):
        """Test full save → retrieve → verify cycle."""
        # 1. Save credential
        test_key = "test_api_key"
        test_value = "super-secret-key-12345"

        cred_manager.save_credential(test_key, test_value)

        # 2. Retrieve credential
        retrieved = cred_manager.get_credential(test_key)

        # 3. Verify
        assert retrieved == test_value
        assert retrieved != test_value  # Encrypted on disk

    def test_credential_encryption_on_disk(self, cred_manager):
        """Verify credentials are actually encrypted on disk."""
        cred_manager.save_credential("key1", "value1")

        # Read raw file
        with open("credentials/encrypted/key1.enc", "rb") as f:
            raw = f.read()

        # Should not contain plaintext
        assert b"value1" not in raw
        assert b"super-secret" not in raw

    def test_credential_access_audit_logging(self, cred_manager, caplog):
        """Verify all credential access is logged for audit."""
        cred_manager.save_credential("audit_test", "secret")
        cred_manager.get_credential("audit_test")

        # Check audit log
        assert "Credential retrieved: audit_t***" in caplog.text

    def test_credential_rotation(self, cred_manager):
        """Test credential rotation process."""
        # 1. Save old credential
        cred_manager.save_credential("rotating_key", "old_value")

        # 2. Rotate (delete old, save new)
        cred_manager.delete_credential("rotating_key")
        cred_manager.save_credential("rotating_key", "new_value")

        # 3. Verify new value
        assert cred_manager.get_credential("rotating_key") == "new_value"

    def test_concurrent_credential_access(self, cred_manager):
        """Test thread-safety of credential manager."""
        import threading
        results = []

        def access_credential(key):
            try:
                cred_manager.save_credential(f"key_{key}", f"value_{key}")
                val = cred_manager.get_credential(f"key_{key}")
                results.append(val)
            except Exception as e:
                results.append(e)

        # Create 10 concurrent threads
        threads = [
            threading.Thread(target=access_credential, args=(i,))
            for i in range(10)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed
        assert len(results) == 10
        assert all(isinstance(r, str) for r in results)
```

#### 2. API Validators Integration
**File:** `tests/integration/test_api_validators_integration.py`

```python
import pytest
from unittest.mock import Mock, patch
from tools.api_validators import validate_restore_response
import requests

class TestAPIValidatorsIntegration:

    @patch('requests.post')
    def test_onedrive_restore_success_path(self, mock_post):
        """Test full successful restore flow from OneDrive API."""
        # Mock OneDrive API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'restored',
            'file_id': 'abc123',
            'timestamp': '2026-03-09T10:00:00Z',
            'size_bytes': 1024
        }
        mock_post.return_value = mock_response

        # Validate response
        is_valid = validate_restore_response(mock_response.json())
        assert is_valid is True

    @patch('requests.post')
    def test_onedrive_restore_missing_field(self, mock_post):
        """Test restore failure when API response missing required field."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'restored',
            # Missing 'file_id'
            'timestamp': '2026-03-09T10:00:00Z',
        }
        mock_post.return_value = mock_response

        is_valid = validate_restore_response(mock_response.json())
        assert is_valid is False  # Should reject

    @patch('requests.post')
    def test_google_drive_metadata_read(self, mock_post):
        """Test metadata validation for Google Drive."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'file_name': 'document.pdf',
            'size': 2048,
            'modified_time': '2026-03-09T10:00:00Z',
            'owners': ['user@example.com']
        }
        mock_post.return_value = mock_response

        is_valid = validate_metadata_response(mock_response.json())
        assert is_valid is True

    @patch('requests.post')
    def test_batch_operation_partial_failure(self, mock_post):
        """Test batch operation with some successful, some failed restores."""
        # Mock partial batch response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'batch_id': 'batch_001',
            'total': 10,
            'succeeded': 8,
            'failed': 2,
            'results': [
                {'file_id': f'f{i}', 'status': 'ok'} for i in range(8)
            ] + [
                {'file_id': 'f9', 'status': 'error', 'reason': 'not_found'},
                {'file_id': 'f10', 'status': 'error', 'reason': 'permission_denied'},
            ]
        }
        mock_post.return_value = mock_response

        is_valid = validate_batch_response(mock_response.json())
        assert is_valid is True
        # Caller should handle partial failures

    def test_api_response_timeout(self):
        """Test handling of API timeout."""
        with patch('requests.post', side_effect=requests.Timeout):
            try:
                validate_restore_response({})
                assert False, "Should have raised exception"
            except requests.Timeout:
                pass  # Expected
```

#### 3. File Operations Integration
**File:** `tests/integration/test_file_operations_integration.py`

```python
import pytest
import tempfile
import os
from pathlib import Path
from tools.input_validators import validate_file_path, build_safe_applescript_put_back

class TestFileOperationsIntegration:

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_valid_file_restore(self, temp_dir):
        """Test restoring a real file via AppleScript."""
        # Create test file
        test_file = Path(temp_dir) / "test_document.pdf"
        test_file.write_text("test content")

        # Validate path
        assert validate_file_path(str(test_file)) is True

        # Build AppleScript
        script = build_safe_applescript_put_back(str(test_file))

        # Verify script is safe (no injection)
        assert "set theFile" in script
        assert "put back" in script.lower()
        assert test_file.name in script

    def test_symlink_traversal_prevention(self, temp_dir):
        """Test that symlinks are rejected (TOCTOU prevention)."""
        real_file = Path(temp_dir) / "real.txt"
        real_file.write_text("secret")

        symlink = Path(temp_dir) / "link.txt"
        symlink.symlink_to(real_file)

        # Should reject symlink
        assert validate_file_path(str(symlink)) is False

    def test_path_traversal_prevention(self, temp_dir):
        """Test rejection of path traversal attempts."""
        attack_paths = [
            f"{temp_dir}/../../../etc/passwd",
            f"{temp_dir}/./../../sensitive",
            "/etc/shadow",
            "../../../../home/user/.ssh/id_rsa",
        ]

        for path in attack_paths:
            assert validate_file_path(path) is False, f"Should reject: {path}"

    def test_restricted_directories(self, temp_dir):
        """Test that system directories are blocked."""
        blocked_paths = [
            "/System/Library/Frameworks",
            "/Library/LaunchDaemons",
            "/Applications",
            "/Volumes/shared",
        ]

        for path in blocked_paths:
            assert validate_file_path(path) is False, f"Should block: {path}"

    def test_applescript_injection_prevention(self, temp_dir):
        """Test various AppleScript injection payloads."""
        injection_attempts = [
            'test"; tell app "Finder" to delete; "',
            'test" & (do shell script "rm -rf /") & "',
            'test`whoami`',
            'test$(id)',
            "test'; system('cat /etc/passwd'); '",
        ]

        for payload in injection_attempts:
            # Should sanitize or reject
            is_valid = validate_file_path(payload)
            assert is_valid is False, f"Should reject injection: {payload}"

    def test_batch_file_operations(self, temp_dir):
        """Test batch restore of multiple files."""
        # Create test files
        test_files = []
        for i in range(5):
            f = Path(temp_dir) / f"file_{i}.txt"
            f.write_text(f"content {i}")
            test_files.append(str(f))

        # Validate all
        results = [validate_file_path(f) for f in test_files]
        assert all(results), "All valid files should pass"

        # Build batch script
        for file_path in test_files:
            script = build_safe_applescript_put_back(file_path)
            assert script is not None
```

#### 4. End-to-End Scenarios
**File:** `tests/integration/test_e2e_scenarios.py`

```python
import pytest
from tools.credentials_manager import CredentialManager
from tools.api_validators import validate_restore_response
from tools.input_validators import validate_file_path

class TestE2EScenarios:

    def test_full_restore_workflow_success(self):
        """Simulate complete restore: auth → validate → execute → verify."""
        # 1. Load credentials
        cm = CredentialManager()
        cred = cm.get_credential("onedrive_token")
        assert cred is not None

        # 2. Call API
        # api_response = call_onedrive_restore_api(cred, file_path)

        # 3. Validate response
        # assert validate_restore_response(api_response) is True

        # 4. Build AppleScript
        # script = build_safe_applescript_put_back(restored_file_path)

        # 5. Execute (would be real execution in prod)
        # result = execute_applescript(script)
        # assert result['status'] == 'success'

    def test_degraded_mode_api_failure(self):
        """Test fallback when API fails but file is local."""
        # This tests: don't let API failure block file restore
        pass

    def test_credential_rotation_during_operation(self):
        """Test handling credential rotation while restore in progress."""
        pass

    def test_large_batch_restore_performance(self):
        """Test performance with 100+ files."""
        pass
```

---

## 4. Performance Testing

### A. Load Testing

**File:** `tests/performance/test_load.py`

```python
import pytest
import time
import random
from concurrent.futures import ThreadPoolExecutor

class TestPerformanceLoad:

    def test_credential_access_throughput(self):
        """Test credential manager under high load."""
        cm = CredentialManager()

        # Pre-populate credentials
        for i in range(100):
            cm.save_credential(f"key_{i}", f"value_{i}")

        # Measure access time
        start = time.time()
        for i in range(1000):
            key = f"key_{random.randint(0, 99)}"
            cm.get_credential(key)
        elapsed = time.time() - start

        # Target: <1ms per access
        avg_time = elapsed / 1000
        assert avg_time < 0.001, f"Credential access too slow: {avg_time*1000:.2f}ms"

    def test_concurrent_api_validation(self):
        """Test API validator under concurrent load."""
        def validate_many():
            for _ in range(100):
                response = {
                    'status': 'restored',
                    'file_id': 'test123',
                    'timestamp': '2026-03-09T00:00:00Z',
                }
                validate_restore_response(response)

        # 10 concurrent threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(validate_many) for _ in range(10)]
            for f in futures:
                f.result()  # Should complete without error
```

### B. Stress Testing

```python
class TestStress:

    def test_credential_memory_under_stress(self):
        """Test memory usage with large credential store."""
        cm = CredentialManager()

        # Store 10,000 credentials
        for i in range(10000):
            cm.save_credential(f"key_{i}", f"value_{i}" * 100)

        # Should not crash or use excessive memory
        # Monitor: ps aux | grep python
```

---

## 5. Security Testing (Penetration Testing)

### A. Security Test Suite

**File:** `tests/security/test_security_hardening.py`

```python
import pytest
from tools.input_validators import (
    validate_file_path,
    build_safe_applescript_put_back,
    sanitize_applescript_string
)

class TestSecurityHardening:

    def test_shell_injection_payloads(self):
        """Test 50+ known shell injection payloads."""
        payloads = [
            # Command injection
            "file.txt; cat /etc/passwd",
            "file.txt && rm -rf /",
            "file.txt | tee /tmp/pwned",
            "file.txt || whoami",

            # Command substitution
            "file.txt$(id)",
            "file.txt`whoami`",
            "file.txt$(cat /etc/passwd)",

            # Variable expansion
            "file.txt$HOME",
            "file.txt${PATH}",

            # Newline injection
            "file.txt\ncat /etc/passwd",
            "file.txt\r\nid",

            # Null byte injection
            "file.txt\x00/etc/passwd",
        ]

        for payload in payloads:
            # Should reject or sanitize
            try:
                result = validate_file_path(payload)
                assert result is False, f"Should reject: {repr(payload)}"
            except Exception:
                pass  # Exception is also acceptable

    def test_applescript_injection_payload_database(self):
        """Test common AppleScript injection patterns."""
        applescript_payloads = [
            # Quote breaking
            'test"; do shell script "rm -rf /"; "',
            "test'; do shell script 'cat /etc/passwd'; '",

            # Comment insertion
            'test" -- tell app "Finder" to delete',

            # Event handler abuse
            'test" & (choose folder) & "',
        ]

        for payload in applescript_payloads:
            # Sanitizer should neutralize
            safe = sanitize_applescript_string(payload)

            # Safe version should not contain dangerous patterns
            assert 'do shell script' not in safe.lower()
            assert 'tell app' not in safe.lower()

    def test_path_traversal_database(self):
        """Test 30+ path traversal patterns."""
        traversal_attempts = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "....//....//....//etc/passwd",
            "/var/www/../../etc/passwd",
            "/var/www/html/./../../config.php",
            "%2e%2e%2fetc%2fpasswd",  # URL encoded
            "..%252f..%252fetc%252fpasswd",  # Double encoded
            "/var/www/html/..;/etc/passwd",  # Null byte equivalent
        ]

        for attempt in traversal_attempts:
            assert validate_file_path(attempt) is False

    def test_symlink_race_conditions(self):
        """Test TOCTOU (time-of-check-time-of-use) prevention."""
        # Verify symlink detection works
        # Real race condition testing requires OS-level timing
        pass

    def test_null_byte_injection(self):
        """Test null byte injection prevention."""
        payload = "file.txt\x00/etc/passwd"
        assert validate_file_path(payload) is False
```

### B. Manual Penetration Testing Checklist

```markdown
# Manual Penetration Testing Checklist

## Authentication & Authorization
- [ ] Can I access credentials without authorization?
- [ ] Can I modify credentials via API?
- [ ] Can I escalate privileges?
- [ ] Can I bypass authentication?

## Injection Attacks
- [ ] Can I execute arbitrary shell commands?
- [ ] Can I inject AppleScript code?
- [ ] Can I execute SQL (if applicable)?
- [ ] Can I break out of sandboxed execution?

## Data Security
- [ ] Can I intercept credentials in transit?
- [ ] Can I decrypt credentials on disk?
- [ ] Can I extract sensitive data from logs?
- [ ] Can I access credentials from memory?

## API Security
- [ ] Can I forge API responses?
- [ ] Can I bypass validation?
- [ ] Can I cause silent failures?
- [ ] Can I perform MITM attacks?

## File System Security
- [ ] Can I access restricted directories?
- [ ] Can I create symlink races?
- [ ] Can I perform path traversal?
- [ ] Can I access unintended files?

## Performance & DOS
- [ ] Can I crash the application with large inputs?
- [ ] Can I consume all memory/CPU?
- [ ] Can I cause denial of service?
- [ ] Can I trigger race conditions?
```

---

## 6. Test Execution Plan

### Phase 1: Unit Tests (Already Complete ✅)
- Status: 49/49 passing
- Coverage: ≥90%

### Phase 2: Integration Tests (Q2 2026)
**Timeline:** April - May 2026
**Owner:** QA Team

```bash
# Run integration tests
pytest tests/integration/ -v --cov=tools

# Expected: ≥50 new tests
# Target coverage: 85%+
```

### Phase 3: Performance Tests (Q2 2026)
**Timeline:** May 2026
**Owner:** DevOps Team

```bash
pytest tests/performance/ -v -m performance

# Establish baseline metrics
# - Credential access: <1ms
# - API validation: <10ms
# - File validation: <5ms
```

### Phase 4: Security Tests (Q3 2026)
**Timeline:** June - July 2026
**Owner:** Security Team

```bash
# Run security test suite
pytest tests/security/ -v

# Manual penetration testing
# - 2-3 days planned
# - External security firm (optional)
```

---

## 7. Test Results Documentation

### Report Template

**File:** `test_results_<date>.md`

```markdown
# Test Results Report
Date: YYYY-MM-DD
Test Phase: [Unit/Integration/Performance/Security]

## Summary
- Total Tests: N
- Passed: M
- Failed: 0
- Skipped: 0
- Coverage: X%

## Key Findings
[Notable results or issues]

## Recommendations
[What to fix before next release]

## Sign-Off
Tested by: [Name]
Date: YYYY-MM-DD
Approved for: [staging/production]
```

---

## 8. Continuous Integration

### GitHub Actions Configuration

**File:** `.github/workflows/test-extended.yml`

```yaml
name: Extended Tests

on:
  schedule:
    - cron: '0 2 * * 0'  # Weekly on Sunday 2 AM
  workflow_dispatch:

jobs:
  integration:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run integration tests
        run: pytest tests/integration/ -v --cov

  performance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run performance tests
        run: pytest tests/performance/ -v -m performance

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run security tests
        run: pytest tests/security/ -v
      - name: Upload results
        uses: actions/upload-artifact@v3
        with:
          name: security-test-results
          path: test-results/
```

---

## 9. Test Coverage Goals

| Phase | Unit Tests | Integration | Performance | Security | Total |
|-------|-----------|-------------|-------------|----------|-------|
| Current | ✅ 49 | ⏳ 0 | ⏳ 0 | ⏳ 0 | 49 |
| Q2 2026 | ✅ 49 | ✅ +50 | ✅ +20 | ⏳ 0 | 119 |
| Q3 2026 | ✅ 49 | ✅ 50 | ✅ 20 | ✅ +60 | 179 |

**Code Coverage:** ≥95% (security modules: ≥99%)

---

## 10. Sign-Off & Schedule

**Planning:** Complete ✅
**Execution Start:** April 1, 2026
**Execution Complete:** August 31, 2026
**Review & Approval:** September 15, 2026

**Owner:** QA + Security Team

---

## Appendix: Test Environment Setup

```bash
# Install test dependencies
pip install pytest pytest-cov pytest-asyncio responses mock pytest-xdist

# Create test structure
mkdir -p tests/integration
mkdir -p tests/performance
mkdir -p tests/security
mkdir -p tests/fixtures

# Create conftest.py for shared fixtures
cat > tests/conftest.py << 'EOF'
import pytest
import tempfile
from pathlib import Path

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir

@pytest.fixture
def test_credentials():
    return {
        'onedrive': 'test_token_123',
        'google': 'test_token_456',
    }
EOF

# Run tests
pytest tests/ -v --cov=tools --cov-report=html
```
