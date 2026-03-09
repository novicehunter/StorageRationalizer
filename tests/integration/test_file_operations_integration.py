"""
Integration tests for input_validators.py file operations.

Tests validate_file_path, validate_directory_path, sanitize_applescript_string,
and build_safe_applescript_put_back using real temp files on disk.
"""

import os

import pytest

from tools.input_validators import (
    InputValidationError,
    build_safe_applescript_put_back,
    sanitize_applescript_string,
    validate_directory_path,
    validate_file_path,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp(tmp_path):
    """Provide a temporary directory (pytest built-in tmp_path)."""
    return tmp_path


@pytest.fixture
def real_file(tmp):
    """A real regular file in the temp directory."""
    f = tmp / "document.pdf"
    f.write_text("test content")
    return f


@pytest.fixture
def real_dir(tmp):
    """A real subdirectory in the temp directory."""
    d = tmp / "subdir"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# validate_file_path — happy paths
# ---------------------------------------------------------------------------


class TestValidateFilePath:
    def test_valid_file_returns_absolute_path(self, real_file):
        result = validate_file_path(str(real_file))
        assert result == str(real_file.resolve())

    def test_relative_path_resolved_to_absolute(self, real_file, tmp):
        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp)
            result = validate_file_path("document.pdf")
            assert os.path.isabs(result)
        finally:
            os.chdir(orig_cwd)

    def test_empty_string_raises(self):
        with pytest.raises(InputValidationError, match="empty"):
            validate_file_path("")

    def test_whitespace_only_raises(self):
        with pytest.raises(InputValidationError, match="empty"):
            validate_file_path("   ")

    def test_nonexistent_file_raises(self, tmp):
        with pytest.raises(InputValidationError, match="does not exist"):
            validate_file_path(str(tmp / "no_such_file.txt"))

    def test_directory_path_raises(self, tmp):
        with pytest.raises(InputValidationError, match="not a file"):
            validate_file_path(str(tmp))

    def test_symlink_raises(self, real_file, tmp):
        link = tmp / "link.pdf"
        link.symlink_to(real_file)
        with pytest.raises(InputValidationError, match="symlink"):
            validate_file_path(str(link))

    def test_shell_semicolon_raises(self, real_file):
        with pytest.raises(InputValidationError, match="metacharacter"):
            validate_file_path(f"{real_file};whoami")

    def test_shell_pipe_raises(self):
        with pytest.raises(InputValidationError, match="metacharacter"):
            validate_file_path("/tmp/file|cat")

    def test_shell_ampersand_raises(self):
        with pytest.raises(InputValidationError, match="metacharacter"):
            validate_file_path("/tmp/file&id")

    def test_shell_backtick_raises(self):
        with pytest.raises(InputValidationError, match="metacharacter"):
            validate_file_path("/tmp/file`whoami`")

    def test_dollar_sign_raises(self):
        with pytest.raises(InputValidationError, match="metacharacter"):
            validate_file_path("/tmp/file$HOME")

    def test_restricted_system_raises(self):
        with pytest.raises(InputValidationError, match="restricted"):
            validate_file_path("/System/Library/something.dylib")

    def test_restricted_library_raises(self):
        with pytest.raises(InputValidationError, match="restricted"):
            validate_file_path("/Library/LaunchDaemons/com.example.plist")

    def test_restricted_applications_raises(self):
        with pytest.raises(InputValidationError, match="restricted"):
            validate_file_path("/Applications/Safari.app/Contents/Info.plist")

    def test_restricted_volumes_raises(self):
        with pytest.raises(InputValidationError, match="restricted"):
            validate_file_path("/Volumes/Backup/file.txt")

    def test_non_string_raises(self):
        with pytest.raises(InputValidationError):
            validate_file_path(12345)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# validate_directory_path — happy paths
# ---------------------------------------------------------------------------


class TestValidateDirectoryPath:
    def test_valid_directory_returns_absolute_path(self, real_dir):
        result = validate_directory_path(str(real_dir))
        assert result == str(real_dir.resolve())

    def test_file_path_raises(self, real_file):
        with pytest.raises(InputValidationError, match="not a directory"):
            validate_directory_path(str(real_file))

    def test_nonexistent_dir_raises(self, tmp):
        with pytest.raises(InputValidationError, match="does not exist"):
            validate_directory_path(str(tmp / "no_such_dir"))

    def test_symlink_dir_raises(self, real_dir, tmp):
        link = tmp / "dir_link"
        link.symlink_to(real_dir)
        with pytest.raises(InputValidationError, match="symlink"):
            validate_directory_path(str(link))

    def test_metacharacter_raises(self):
        with pytest.raises(InputValidationError, match="metacharacter"):
            validate_directory_path("/tmp/dir;id")

    def test_restricted_system_raises(self):
        with pytest.raises(InputValidationError, match="restricted"):
            validate_directory_path("/System/Library")


# ---------------------------------------------------------------------------
# sanitize_applescript_string
# ---------------------------------------------------------------------------


class TestSanitizeApplescriptString:
    def test_plain_string_unchanged(self):
        assert sanitize_applescript_string("hello world") == "hello world"

    def test_double_quote_escaped(self):
        assert sanitize_applescript_string('say "hello"') == 'say \\"hello\\"'

    def test_backslash_escaped(self):
        assert sanitize_applescript_string("path\\to\\file") == "path\\\\to\\\\file"

    def test_backslash_then_quote(self):
        result = sanitize_applescript_string('\\"')
        assert "\\\\" in result  # backslash must be escaped before quote

    def test_empty_string(self):
        assert sanitize_applescript_string("") == ""

    def test_injection_payload_quote_breaking(self):
        payload = 'test"; do shell script "rm -rf /"'
        safe = sanitize_applescript_string(payload)
        assert '"' not in safe.replace('\\"', "")  # all bare quotes removed

    def test_injection_payload_no_shell_script_executable(self):
        payload = '"; do shell script "id"; "'
        safe = sanitize_applescript_string(payload)
        # When embedded in AppleScript "...", escaped quotes cannot break out
        assert '\\"' in safe or '"' not in safe.replace('\\"', "")


# ---------------------------------------------------------------------------
# build_safe_applescript_put_back
# ---------------------------------------------------------------------------


class TestBuildSafeApplescriptPutBack:
    def test_returns_applescript_string(self, real_file, real_dir):
        script = build_safe_applescript_put_back(str(real_file), str(real_dir))
        assert isinstance(script, str)
        assert len(script) > 0

    def test_script_contains_finder_tell_block(self, real_file, real_dir):
        script = build_safe_applescript_put_back(str(real_file), str(real_dir))
        assert 'tell application "Finder"' in script
        assert "end tell" in script

    def test_script_contains_move_command(self, real_file, real_dir):
        script = build_safe_applescript_put_back(str(real_file), str(real_dir))
        assert "move" in script

    def test_script_contains_posix_file_references(self, real_file, real_dir):
        script = build_safe_applescript_put_back(str(real_file), str(real_dir))
        assert "POSIX file" in script

    def test_file_path_in_script(self, real_file, real_dir):
        script = build_safe_applescript_put_back(str(real_file), str(real_dir))
        assert real_file.name in script

    def test_invalid_file_path_raises(self, tmp, real_dir):
        with pytest.raises(InputValidationError):
            build_safe_applescript_put_back(str(tmp / "nonexistent.pdf"), str(real_dir))

    def test_invalid_destination_raises(self, real_file, tmp):
        with pytest.raises(InputValidationError):
            build_safe_applescript_put_back(str(real_file), str(tmp / "nonexistent_dir"))

    def test_symlink_file_raises(self, real_file, real_dir, tmp):
        link = tmp / "link.pdf"
        link.symlink_to(real_file)
        with pytest.raises(InputValidationError, match="symlink"):
            build_safe_applescript_put_back(str(link), str(real_dir))

    def test_symlink_destination_raises(self, real_file, real_dir, tmp):
        link = tmp / "dir_link"
        link.symlink_to(real_dir)
        with pytest.raises(InputValidationError, match="symlink"):
            build_safe_applescript_put_back(str(real_file), str(link))

    def test_batch_of_files(self, tmp, real_dir):
        """All valid files in a batch should produce scripts."""
        files = []
        for i in range(5):
            f = tmp / f"file_{i}.txt"
            f.write_text(f"content {i}")
            files.append(f)

        scripts = [build_safe_applescript_put_back(str(f), str(real_dir)) for f in files]
        assert len(scripts) == 5
        assert all("Finder" in s for s in scripts)
