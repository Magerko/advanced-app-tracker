"""Exit-password hashing.

Uses :mod:`bcrypt` when available and transparently falls back to salted
SHA-256 otherwise. Hashes are self-describing (bcrypt hashes start with ``$2``)
so a database created with one backend keeps working if the other is used.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os

log = logging.getLogger(__name__)

try:
    import bcrypt
    _BCRYPT_AVAILABLE = True
except ImportError:
    bcrypt = None  # type: ignore
    _BCRYPT_AVAILABLE = False
    log.warning("bcrypt not installed; falling back to salted SHA-256.")

# Marker prefix for the SHA-256 fallback: "sha256$<hex-salt>$<hex-digest>".
_SHA_PREFIX = b"sha256$"


def hash_password(password: str) -> bytes:
    pwd = password.encode("utf-8")
    if _BCRYPT_AVAILABLE:
        return bcrypt.hashpw(pwd, bcrypt.gensalt())
    salt = os.urandom(16)
    digest = hashlib.sha256(salt + pwd).hexdigest().encode("ascii")
    return _SHA_PREFIX + salt.hex().encode("ascii") + b"$" + digest


def check_password(stored_hash: bytes, provided_password: str) -> bool:
    if not stored_hash or not provided_password:
        return False
    pwd = provided_password.encode("utf-8")

    if stored_hash.startswith(_SHA_PREFIX):
        try:
            _, salt_hex, digest = stored_hash.split(b"$", 2)
            salt = bytes.fromhex(salt_hex.decode("ascii"))
            expected = hashlib.sha256(salt + pwd).hexdigest().encode("ascii")
            return hmac.compare_digest(expected, digest)
        except (ValueError, AttributeError):
            return False

    if _BCRYPT_AVAILABLE:
        try:
            return bcrypt.checkpw(pwd, stored_hash)
        except ValueError:
            log.warning("Stored hash is not valid bcrypt.")
            return False
    log.error("bcrypt hash present but bcrypt is not installed; cannot verify.")
    return False
