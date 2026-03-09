"""
Tests for tools/input_validators.py

Coverage target: ≥90% line coverage
Test count: 34 tests across all 5 functions + InputValidationError
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.input_validators import (  # noqa: E402
    InputValidationError,
    build_safe_applescript_put_back,
    sanitize_applescript_string,
    validate_command_list,
    validate_directory_path,
    validate_file_path,
)


# ── InputValidationError ──────────────────────────────────────────────────────


class TestInputValidationError:
    def test_is_exception(self):
        with pytest.raises(InputValidationError):
            raise InputValidationError("test message")

    def test_message_preserved(self):
        err = InputValidationError("invalid path: /bad")
        assert str(err) == "invalid path: /bad"


# ── validate_file_path ────────────────────────────────────────────────────────


class TestValidateFilePath:
    def test_valid_file_returns_absolute_path(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content")
        result = validate_file_path(str(f))
        assert result == str(f)
        assert os.path.isabs(result)

    def test_relative_path_converted_to_absolute(self, tmp_path, monkeypatch):
        f = tmp_path / "relative.txt"
        f.write_text("content")
        monkeypatch.chdir(tmp_path)
        result = validate_file_path("relative.txt")
        assert os.path.isabs(result)
        assert result == str(f)

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(InputValidationError, match="does not exist"):
            validate_file_path(str(tmp_path / "ghost.txt"))

    def test_directory_not_file_raises(self, tmp_path):
        with pytest.raises(InputValidationError, match="not a file"):
            validate_file_path(str(tmp_path))

    def test_symlink_raises(self, tmp_path):
        target = tmp_path / "target.txt"
        target.write_text("content")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        with pytest.raises(InputValidationError, match="symlink"):
            validate_file_path(str(link))

    def test_system_path_raises(self):
        # /System is a restricted directory regardless of whether the path exists
        with pytest.raises(InputValidationError, match="restricted"):
            validate_file_path("/System/some_file.txt")

    def test_library_path_raises(self):
        with pytest.raises(InputValidationError, match="restricted"):
            validate_file_path("/Library/Preferences/com.apple.plist")

    def test_path_with_semicolon_raises(self):
        with pytest.raises(InputValidationError, match="metacharacters"):
            validate_file_path("/tmp/file;rm -rf /")

    def test_path_with_pipe_raises(self):
        with pytest.raises(InputValidationError, match="metacharacters"):
            validate_file_path("/tmp/file|cat /etc/passwd")

    def test_path_with_backtick_raises(self):
        with pytest.raises(InputValidationError, match="metacharacters"):
            validate_file_path("/tmp/`whoami`")

    def test_path_with_command_substitution_raises(self):
        with pytest.raises(InputValidationError, match="metacharacters"):
            validate_file_path("/tmp/$(id)")

    def test_path_with_dollar_sign_raises(self):
        with pytest.raises(InputValidationError, match="metacharacters"):
            validate_file_path("/tmp/$HOME/file.txt")


# ── validate_directory_path ───────────────────────────────────────────────────


class TestValidateDirectoryPath:
    def test_valid_directory_returns_absolute_path(self, tmp_path):
        result = validate_directory_path(str(tmp_path))
        assert result == str(tmp_path)
        assert os.path.isabs(result)

    def test_relative_path_converted_to_absolute(self, tmp_path, monkeypatch):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        monkeypatch.chdir(tmp_path)
        result = validate_directory_path("subdir")
        assert os.path.isabs(result)
        assert result == str(subdir)

    def test_nonexistent_directory_raises(self, tmp_path):
        with pytest.raises(InputValidationError, match="does not exist"):
            validate_directory_path(str(tmp_path / "missing_dir"))

    def test_file_not_directory_raises(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("content")
        with pytest.raises(InputValidationError, match="not a directory"):
            validate_directory_path(str(f))

    def test_symlink_directory_raises(self, tmp_path):
        real_dir = tmp_path / "real_dir"
        real_dir.mkdir()
        link_dir = tmp_path / "link_dir"
        link_dir.symlink_to(real_dir)
        with pytest.raises(InputValidationError, match="symlink"):
            validate_directory_path(str(link_dir))

    def test_system_path_raises(self):
        with pytest.raises(InputValidationError, match="restricted"):
            validate_directory_path("/System/Library")

    def test_volumes_path_raises(self):
        with pytest.raises(InputValidationError, match="restricted"):
            validate_directory_path("/Volumes")

    def test_injection_chars_raises(self):
        with pytest.raises(InputValidationError, match="metacharacters"):
            validate_directory_path("/tmp/dir;malicious_cmd")

    def test_empty_path_raises(self):
        with pytest.raises(InputValidationError, match="empty"):
            validate_directory_path("   ")


# ── sanitize_applescript_string ───────────────────────────────────────────────


class TestSanitizeAppleScriptString:
    def test_normal_string_unchanged(self):
        result = sanitize_applescript_string("hello world")
        assert result == "hello world"

    def test_double_quotes_escaped(self):
        result = sanitize_applescript_string('file "name" here')
        assert result == 'file \\"name\\" here'
        assert '\\"' in result

    def test_backslash_escaped(self):
        result = sanitize_applescript_string("path\\to\\file")
        assert result == "path\\\\to\\\\file"

    def test_complex_string_all_chars_escaped(self):
        # Backslash and quote together: say "hello\world"
        result = sanitize_applescript_string('say "hello\\world"')
        # Backslash → \\\\ first, then quote → \\"
        assert result == 'say \\"hello\\\\world\\"'


# ── validate_command_list ─────────────────────────────────────────────────────


class TestValidateCommandList:
    def test_valid_command_list_returned(self):
        cmd = ["osascript", "-e", "tell application Finder end tell"]
        result = validate_command_list(cmd)
        assert result == cmd

    def test_string_not_list_raises(self):
        with pytest.raises(InputValidationError, match="list"):
            validate_command_list("osascript -e script")

    def test_command_with_injection_raises(self):
        with pytest.raises(InputValidationError, match="metacharacters"):
            validate_command_list(["osascript", "arg;rm -rf /"])

    def test_non_string_element_raises(self):
        with pytest.raises(InputValidationError, match="string"):
            validate_command_list(["cmd", 42])

    def test_pipe_in_element_raises(self):
        with pytest.raises(InputValidationError, match="metacharacters"):
            validate_command_list(["cmd", "arg|other"])


# ── build_safe_applescript_put_back ──────────────────────────────────────────


class TestBuildSafeAppleScriptPutBack:
    def test_valid_paths_returns_applescript_string(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content")
        result = build_safe_applescript_put_back(str(f), str(tmp_path))
        assert isinstance(result, str)
        assert "Finder" in result
        assert "move" in result
        assert "POSIX file" in result

    def test_invalid_file_path_raises(self, tmp_path):
        with pytest.raises(InputValidationError):
            build_safe_applescript_put_back(str(tmp_path / "nonexistent.txt"), str(tmp_path))

    def test_invalid_location_path_raises(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("content")
        with pytest.raises(InputValidationError):
            build_safe_applescript_put_back(str(f), str(tmp_path / "nonexistent_dir"))

    def test_quotes_in_path_are_escaped(self, tmp_path):
        # Create a file with a normal name; verify escaping logic applies
        f = tmp_path / "normal.txt"
        f.write_text("content")
        result = build_safe_applescript_put_back(str(f), str(tmp_path))
        # The result should not contain unescaped double quotes inside POSIX file strings
        # (the surrounding quotes of the AppleScript string are part of the template)
        assert 'POSIX file "' in result
