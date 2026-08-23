"""Password hashing and fail-closed verification helpers for the Web UI."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)

# Default PBKDF2 iterations adhering to OWASP recommended baseline
DEFAULT_PBKDF2_ITERATIONS = 600_000


def hash_password(password: str, iterations: int = DEFAULT_PBKDF2_ITERATIONS) -> str:
    """Generate secure PBKDF2-HMAC-SHA256 password hash with random salt."""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return f"pbkdf2:sha256:{iterations}${salt}${dk.hex()}"


def _verify_pbkdf2(password: str, hash_str: str) -> bool:
    """Verify password against pbkdf2 format string."""
    try:
        parts = hash_str.split("$")
        if len(parts) != 3:
            return False
        algo_part, salt_hex, hash_hex = parts
        algo_tokens = algo_part.split(":")
        iterations = int(algo_tokens[2]) if len(algo_tokens) >= 3 else DEFAULT_PBKDF2_ITERATIONS
        hash_name = algo_tokens[1] if len(algo_tokens) >= 2 else "sha256"

        dk = hashlib.pbkdf2_hmac(
            hash_name,
            password.encode("utf-8"),
            salt_hex.encode("utf-8"),
            iterations,
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception as exc:
        logger.warning("Error verifying PBKDF2 hash: %s", exc)
        return False


def _verify_argon2(password: str, hash_str: str) -> bool:
    """Verify password against Argon2id hash if argon2-cffi is installed."""
    try:
        from argon2 import PasswordHasher  # type: ignore[import-not-found]
        from argon2.exceptions import VerifyMismatchError  # type: ignore[import-not-found]

        ph = PasswordHasher()
        try:
            ph.verify(hash_str, password)
            return True
        except VerifyMismatchError:
            return False
    except ImportError:
        logger.error("Argon2 hash provided but argon2-cffi package is not installed")
        return False
    except Exception as exc:
        logger.warning("Error verifying Argon2 hash: %s", exc)
        return False


def _verify_bcrypt(password: str, hash_str: str) -> bool:
    """Verify password against bcrypt hash if bcrypt is installed."""
    try:
        import bcrypt  # type: ignore[import-not-found]

        return bool(bcrypt.checkpw(password.encode("utf-8"), hash_str.encode("utf-8")))
    except ImportError:
        logger.error("Bcrypt hash provided but bcrypt package is not installed")
        return False
    except Exception as exc:
        logger.warning("Error verifying bcrypt hash: %s", exc)
        return False


def verify_password(
    plain_password: str,
    admin_password: str = "",
    admin_password_hash: str | None = None,
) -> bool:
    """
    Constant-time, fail-closed password verification.

    Returns False immediately if no password or hash is configured.
    """
    if not plain_password:
        return False

    if not admin_password and not admin_password_hash:
        logger.error("Authentication attempted but no admin password or hash is configured")
        return False

    # Check plaintext password if set
    if admin_password and secrets.compare_digest(plain_password, admin_password):
        return True

    # Check hashed password if set
    if admin_password_hash:
        clean_hash = admin_password_hash.strip()
        if clean_hash.startswith("pbkdf2:"):
            return _verify_pbkdf2(plain_password, clean_hash)
        if clean_hash.startswith("$argon2"):
            return _verify_argon2(plain_password, clean_hash)
        if clean_hash.startswith(("$2a$", "$2b$", "$2y$")):
            return _verify_bcrypt(plain_password, clean_hash)
        # Fallback to pbkdf2 format if formatted as iterations$salt$hash
        if "$" in clean_hash:
            return _verify_pbkdf2(plain_password, clean_hash)

    return False


def is_auth_configured(settings: Settings) -> bool:
    """Check whether authentication credentials are explicitly configured."""
    return bool(settings.admin_password or settings.admin_password_hash)
