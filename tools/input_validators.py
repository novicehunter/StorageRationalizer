#!/usr/bin/env python3
"""
StorageRationalizer — Input Validation Module

Centralized validation for all shell/AppleScript operations.
Prevents injection attacks via shell metacharacters, symlink attacks,
and path traversal into restricted system directories.
"""

import os
import re

# Shell metacharacters that could enable command injection
_SHELL_METACHARACTERS = re.compile(r"[;|&`$<>]")

# Restricted system directories — off-limits for all file operations
_RESTRICTED_DIRS = ("/System", "/Library", "/Volumes", "/Applications")


class InputValidationError(Exception):
    """Raised when user input fails security validation."""

    pass


def validate_file_path(path: str) -> str:
    """
    Validate a file path for safe use in shell operations.

    Checks:
    - path is a non-empty string
    - no shell metacharacters (prevents injection)
    - not in restricted system directories (/System, /Library, /Volumes, /Applications)
    - not a symlink (prevents TOCTOU attacks)
    - exists on disk
    - is a regular file (not a directory)

    Returns: sanitized absolute path string
    Raises: InputValidationError with descriptive message if any check fails
    """
    if not isinstance(path, str):
        raise InputValidationError(f"Path must be a string, got {type(path).__name__}: {path!r}")

    if not path.strip():
        raise InputValidationError("Path cannot be empty")

    if _SHELL_METACHARACTERS.search(path):
        raise InputValidationError(f"Path contains shell metacharacters: {path!r}")

    abs_path = os.path.abspath(path)

    for restricted in _RESTRICTED_DIRS:
        if abs_path == restricted or abs_path.startswith(restricted + os.sep):
            raise InputValidationError(f"Path is in restricted directory {restricted!r}: {path!r}")

    # Check symlink BEFORE existence (os.path.exists follows symlinks)
    if os.path.islink(abs_path):
        raise InputValidationError(f"Path is a symlink (security risk): {path!r}")

    if not os.path.exists(abs_path):
        raise InputValidationError(f"Path does not exist: {path!r}")

    if not os.path.isfile(abs_path):
        raise InputValidationError(f"Path is not a file: {path!r}")

    return abs_path


def validate_directory_path(path: str) -> str:
    """
    Validate a directory path for safe use in shell operations.

    Checks:
    - path is a non-empty string
    - no shell metacharacters (prevents injection)
    - not in restricted system directories (/System, /Library, /Volumes, /Applications)
    - not a symlink (prevents TOCTOU attacks)
    - exists on disk
    - is a directory (not a file)

    Returns: sanitized absolute path string
    Raises: InputValidationError with descriptive message if any check fails
    """
    if not isinstance(path, str):
        raise InputValidationError(f"Path must be a string, got {type(path).__name__}: {path!r}")

    if not path.strip():
        raise InputValidationError("Path cannot be empty")

    if _SHELL_METACHARACTERS.search(path):
        raise InputValidationError(f"Path contains shell metacharacters: {path!r}")

    abs_path = os.path.abspath(path)

    for restricted in _RESTRICTED_DIRS:
        if abs_path == restricted or abs_path.startswith(restricted + os.sep):
            raise InputValidationError(f"Path is in restricted directory {restricted!r}: {path!r}")

    # Check symlink BEFORE existence (os.path.exists follows symlinks)
    if os.path.islink(abs_path):
        raise InputValidationError(f"Path is a symlink (security risk): {path!r}")

    if not os.path.exists(abs_path):
        raise InputValidationError(f"Path does not exist: {path!r}")

    if not os.path.isdir(abs_path):
        raise InputValidationError(f"Path is not a directory: {path!r}")

    return abs_path


def sanitize_applescript_string(s: str) -> str:
    """
    Escape a string for safe inclusion in AppleScript double-quoted strings.

    Escapes (in order):
    - Backslashes: \\ → \\\\  (must be first to avoid double-escaping)
    - Double quotes: " → \\"

    Returns: safely escaped string suitable for use inside AppleScript "..."
    """
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    return s


def validate_command_list(cmd_list: list) -> list:
    """
    Validate a shell command list for safe use with subprocess.run(shell=False).

    Using a list (not a string) with shell=False bypasses shell interpretation entirely.
    This function enforces that pattern and ensures no element contains metacharacters.

    Checks:
    - cmd_list is a list (not a string — prevents accidental shell=True-style usage)
    - all elements are strings
    - no element contains shell metacharacters

    Returns: validated command list unchanged
    Raises: InputValidationError if any check fails
    """
    if not isinstance(cmd_list, list):
        raise InputValidationError(
            f"Command must be a list, not {type(cmd_list).__name__}: {cmd_list!r}"
        )

    for i, element in enumerate(cmd_list):
        if not isinstance(element, str):
            raise InputValidationError(
                f"Command element {i} must be a string, "
                f"got {type(element).__name__}: {element!r}"
            )
        if _SHELL_METACHARACTERS.search(element):
            raise InputValidationError(
                f"Command element {i} contains shell metacharacters: {element!r}"
            )

    return cmd_list


def build_safe_applescript_put_back(file_path: str, original_location: str) -> str:
    """
    Build a safe AppleScript command to move a known file to its original location.

    Validates both paths exist and escapes them for use in AppleScript quoted strings.
    Use this when the exact trash path is known. For name-based Finder Trash searches,
    use sanitize_applescript_string() directly.

    Args:
        file_path: absolute path to the file to move (must exist)
        original_location: absolute path to the destination directory (must exist)

    Returns: AppleScript string that moves the file to the original location
    Raises: InputValidationError if either path is invalid
    """
    safe_file = validate_file_path(file_path)
    safe_location = validate_directory_path(original_location)

    escaped_file = sanitize_applescript_string(safe_file)
    escaped_location = sanitize_applescript_string(safe_location)

    script = (
        f'tell application "Finder"\n'
        f'    move POSIX file "{escaped_file}" to POSIX file "{escaped_location}"\n'
        f"end tell"
    )
    return script
