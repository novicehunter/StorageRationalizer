"""
credentials_manager.py — Encrypted credential storage for StorageRationalizer.

Stores service credentials encrypted with AES-256-GCM. Master password is
derived via PBKDF2-HMAC-SHA256 and cached in memory for 60 minutes.

File layout:
    credentials/encrypted/{service}.enc  — ciphertext
    credentials/encrypted/{service}.meta — JSON with salt + iv (hex-encoded)

Usage:
    from tools.credentials_manager import CredentialsManager

    cm = CredentialsManager()
    cm.save("google", "client_secret", "abc123")
    secret = cm.load("google", "client_secret")
    cm.clear_cache()

Dependencies:
    pip install cryptography
"""

from __future__ import annotations

import getpass
import json
import secrets
import sys
import time
from pathlib import Path
from typing import Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    from cryptography.exceptions import InvalidTag
except ImportError:
    sys.exit(
        "ERROR: 'cryptography' package not found.\n" "Install it with:  pip install cryptography"
    )

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PBKDF2_ITERATIONS = 600_000  # OWASP 2023 recommendation for SHA-256
_SALT_BYTES = 32
_IV_BYTES = 12  # AES-GCM standard nonce length
_KEY_BYTES = 32  # AES-256
_CACHE_TTL_SECONDS = 3600  # 60 minutes
_MAX_RETRIES = 3


def _repo_root() -> Path:
    """Return the repository root regardless of OS or working directory."""
    return Path(__file__).resolve().parent.parent


def _encrypted_dir() -> Path:
    """Return the path to the encrypted credentials directory, creating it if needed."""
    d = _repo_root() / "credentials" / "encrypted"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


def _derive_key(password: str, salt: bytes) -> bytes:
    """
    Derive a 256-bit AES key from *password* and *salt* using PBKDF2-HMAC-SHA256.

    Args:
        password: The master password string (UTF-8 encoded internally).
        salt:     Random 32-byte salt unique to each encrypted file.

    Returns:
        32-byte derived key suitable for AES-256-GCM.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_BYTES,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


# ---------------------------------------------------------------------------
# Low-level encrypt / decrypt
# ---------------------------------------------------------------------------


def _encrypt(plaintext: str, password: str) -> tuple[bytes, bytes, bytes]:
    """
    Encrypt *plaintext* with AES-256-GCM.

    Args:
        plaintext: UTF-8 string to encrypt.
        password:  Master password.

    Returns:
        Tuple of (ciphertext_bytes, salt_bytes, iv_bytes).
    """
    salt = secrets.token_bytes(_SALT_BYTES)
    iv = secrets.token_bytes(_IV_BYTES)
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
    return ciphertext, salt, iv


def _decrypt(ciphertext: bytes, salt: bytes, iv: bytes, password: str) -> str:
    """
    Decrypt AES-256-GCM *ciphertext*.

    Args:
        ciphertext: Raw ciphertext bytes (includes GCM authentication tag).
        salt:       Salt used during encryption.
        iv:         IV (nonce) used during encryption.
        password:   Master password.

    Returns:
        Decrypted UTF-8 string.

    Raises:
        ValueError: If the password is wrong or the ciphertext is tampered.
    """
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    try:
        plaintext_bytes = aesgcm.decrypt(iv, ciphertext, None)
    except InvalidTag as exc:
        raise ValueError("Wrong password or corrupted data.") from exc
    return plaintext_bytes.decode("utf-8")


# ---------------------------------------------------------------------------
# Legacy plaintext detection
# ---------------------------------------------------------------------------

_LEGACY_FILES: dict[str, Path] = {
    "google": _repo_root() / "credentials" / "google_credentials.json",
    "google_token": _repo_root() / "credentials" / "google_token.json",
    "onedrive": _repo_root() / "credentials" / "onedrive_credentials.txt",
    "onedrive_token": _repo_root() / "credentials" / "onedrive_token.json",
}


def _find_legacy_files() -> list[tuple[str, Path]]:
    """Return list of (service_name, path) for legacy plaintext credential files that exist."""
    found = []
    for service, path in _LEGACY_FILES.items():
        if path.exists():
            found.append((service, path))
    return found


# ---------------------------------------------------------------------------
# CredentialsManager
# ---------------------------------------------------------------------------


class CredentialsManager:
    """
    Encrypted credential store using AES-256-GCM with PBKDF2 key derivation.

    Credentials are stored as JSON objects keyed by *service*. Each service
    gets its own encrypted file so a single compromised file does not expose
    all credentials.

    Master password is cached in memory for ``_CACHE_TTL_SECONDS`` (60 min)
    to avoid re-prompting on every operation. Call :meth:`clear_cache` to
    evict it immediately.

    Thread safety: not guaranteed. Intended for single-process, interactive
    CLI use.

    Args:
        encrypted_dir: Override the default encrypted-files directory
                       (useful for testing).
    """

    def __init__(self, encrypted_dir: Optional[Path] = None) -> None:
        self._dir: Path = encrypted_dir if encrypted_dir is not None else _encrypted_dir()
        self._cached_password: Optional[str] = None
        self._cache_ts: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, service: str, key: str) -> str:
        """
        Load a single credential value.

        Args:
            service: Logical service name, e.g. ``"google"``, ``"onedrive"``.
            key:     Key within the service namespace, e.g. ``"client_secret"``.

        Returns:
            The stored string value.

        Raises:
            KeyError:    If *service* or *key* does not exist.
            RuntimeError: If decryption fails after all retries.
        """
        data = self._load_service_data(service)
        if key not in data:
            raise KeyError(f"Key '{key}' not found in service '{service}'.")
        return data[key]

    def save(self, service: str, key: str, value: str) -> None:
        """
        Save a credential value, creating or updating the encrypted file.

        If the encrypted file for *service* already exists it is decrypted,
        the key is inserted/updated, and the file is re-encrypted. This means
        the master password is required even for writes when existing data
        must be preserved.

        Args:
            service: Logical service name.
            key:     Key within the service namespace.
            value:   String value to store.

        Raises:
            RuntimeError: If decryption of an existing file fails after all retries.
        """
        enc_path = self._enc_path(service)

        # Merge with existing data if the file already exists
        if enc_path.exists():
            data = self._load_service_data(service)
        else:
            data = {}

        data[key] = value
        self._write_service_data(service, data)
        print(f"[credentials_manager] Saved '{key}' for service '{service}'.")

    def clear_cache(self) -> None:
        """
        Evict the cached master password from memory immediately.

        The next call to :meth:`load` or :meth:`save` will re-prompt for the
        password.
        """
        self._cached_password = None
        self._cache_ts = 0.0
        print("[credentials_manager] Password cache cleared.")

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    def migrate_legacy(self, dry_run: bool = False) -> list[str]:
        """
        Auto-migrate legacy plaintext credential files into the encrypted store.

        Each legacy file is read as raw text and stored under the key
        ``"raw_content"`` within its service namespace. After successful
        migration the original file is *not* deleted — removal is the
        operator's responsibility.

        Args:
            dry_run: If True, report what would be migrated without writing.

        Returns:
            List of service names that were (or would be) migrated.
        """
        migrated: list[str] = []
        legacy = _find_legacy_files()

        if not legacy:
            print("[credentials_manager] No legacy credential files found.")
            return migrated

        for service, path in legacy:
            enc_path = self._enc_path(service)
            if enc_path.exists():
                print(f"[credentials_manager] SKIP '{service}' — encrypted file already exists.")
                continue

            content = path.read_text(encoding="utf-8")
            if dry_run:
                print(f"[credentials_manager] DRY-RUN would migrate: {path} → service='{service}'")
            else:
                self._write_service_data(service, {"raw_content": content})
                print(f"[credentials_manager] Migrated '{path.name}' → service='{service}'.")
            migrated.append(service)

        return migrated

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _enc_path(self, service: str) -> Path:
        """Return the path to the .enc file for *service*."""
        return self._dir / f"{service}.enc"

    def _meta_path(self, service: str) -> Path:
        """Return the path to the .meta file for *service*."""
        return self._dir / f"{service}.meta"

    def _get_password(self) -> str:
        """
        Return the master password, using the in-memory cache when valid.

        Prompts the user interactively when the cache has expired or was never set.

        Returns:
            Master password string.
        """
        now = time.monotonic()
        if self._cached_password and (now - self._cache_ts) < _CACHE_TTL_SECONDS:
            return self._cached_password

        # Cache expired or not set — prompt
        print("[credentials_manager] Master password required (cached for 60 min).")
        password = getpass.getpass("Master password: ")
        self._cached_password = password
        self._cache_ts = now
        return password

    def _invalidate_cache(self) -> None:
        """Evict cached password without printing a message (used internally on auth failure)."""
        self._cached_password = None
        self._cache_ts = 0.0

    def _load_service_data(self, service: str) -> dict[str, str]:
        """
        Decrypt and return all key-value pairs for *service*.

        Retries up to ``_MAX_RETRIES`` times on wrong password before raising.

        Args:
            service: Service name.

        Returns:
            Dict of key → value strings.

        Raises:
            FileNotFoundError: If no encrypted file exists for *service*.
            RuntimeError:      If decryption fails after all retries.
        """
        enc_path = self._enc_path(service)
        meta_path = self._meta_path(service)

        if not enc_path.exists():
            raise FileNotFoundError(
                f"No credentials found for service '{service}'. "
                f"Run save() first or migrate legacy files."
            )

        if not meta_path.exists():
            raise FileNotFoundError(
                f"Metadata file missing for service '{service}' ({meta_path}). "
                "The encrypted store may be corrupted."
            )

        # Load metadata
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            salt = bytes.fromhex(meta["salt"])
            iv = bytes.fromhex(meta["iv"])
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Corrupted metadata for service '{service}': {exc}") from exc

        ciphertext = enc_path.read_bytes()

        # Retry loop
        for attempt in range(1, _MAX_RETRIES + 1):
            password = self._get_password()
            try:
                plaintext = _decrypt(ciphertext, salt, iv, password)
                return json.loads(plaintext)
            except ValueError:
                self._invalidate_cache()
                remaining = _MAX_RETRIES - attempt
                if remaining > 0:
                    print(
                        f"[credentials_manager] Wrong password. "
                        f"{remaining} attempt(s) remaining."
                    )
                else:
                    raise RuntimeError(
                        f"Failed to decrypt credentials for service '{service}' "
                        f"after {_MAX_RETRIES} attempts."
                    )
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Decrypted data for service '{service}' is not valid JSON. "
                    "The file may be corrupted."
                ) from exc

        # Unreachable, but satisfies type checkers
        raise RuntimeError("Unexpected error in _load_service_data.")

    def _write_service_data(self, service: str, data: dict[str, str]) -> None:
        """
        Encrypt and write *data* for *service*.

        Args:
            service: Service name.
            data:    Dict of key → value strings to encrypt.
        """
        password = self._get_password()
        plaintext = json.dumps(data, ensure_ascii=False)
        ciphertext, salt, iv = _encrypt(plaintext, password)

        enc_path = self._enc_path(service)
        meta_path = self._meta_path(service)

        enc_path.write_bytes(ciphertext)
        meta_path.write_text(
            json.dumps({"salt": salt.hex(), "iv": iv.hex()}, indent=2),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _cli() -> None:
    """Minimal CLI for managing credentials from the terminal."""
    import argparse

    parser = argparse.ArgumentParser(
        description="StorageRationalizer credential manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/credentials_manager.py save google client_secret abc123
  python tools/credentials_manager.py load google client_secret
  python tools/credentials_manager.py migrate
  python tools/credentials_manager.py migrate --dry-run
  python tools/credentials_manager.py clear-cache
""",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # save
    p_save = sub.add_parser("save", help="Save a credential value")
    p_save.add_argument("service", help="Service name (e.g. google)")
    p_save.add_argument("key", help="Credential key (e.g. client_secret)")
    p_save.add_argument("value", help="Credential value")

    # load
    p_load = sub.add_parser("load", help="Load a credential value")
    p_load.add_argument("service")
    p_load.add_argument("key")

    # migrate
    p_migrate = sub.add_parser("migrate", help="Migrate legacy plaintext files")
    p_migrate.add_argument("--dry-run", action="store_true")

    # clear-cache
    sub.add_parser("clear-cache", help="Clear the in-memory password cache")

    args = parser.parse_args()
    cm = CredentialsManager()

    if args.command == "save":
        cm.save(args.service, args.key, args.value)
    elif args.command == "load":
        value = cm.load(args.service, args.key)
        print(value)
    elif args.command == "migrate":
        migrated = cm.migrate_legacy(dry_run=args.dry_run)
        if migrated:
            print(f"Migrated services: {', '.join(migrated)}")
    elif args.command == "clear-cache":
        cm.clear_cache()


if __name__ == "__main__":
    _cli()
