"""
Encryption utility for sensitive data (SSH passwords, etc.).

Uses Fernet symmetric encryption (cryptography library).
The key is derived from the app's SECRET_KEY setting.
Password fields are stored encrypted in the DB and decrypted on read.
"""

import base64
import hashlib

from app.core.logging import get_logger

logger = get_logger(__name__)

# Lazy-initialized Fernet instance
_fernet = None


def _get_fernet():
    """Get or initialize the Fernet instance from the app's SECRET_KEY."""
    global _fernet
    if _fernet is not None:
        return _fernet

    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise ImportError(
            "cryptography package is required for SSH password encryption. "
            "Install it with: pip install cryptography"
        )
    from app.core.config import settings

    # Derive a valid Fernet key (32 url-safe base64 bytes) from SECRET_KEY
    key_material = settings.secret_key.encode("utf-8")
    # Use SHA256 to get 32 bytes, then base64-encode for Fernet
    derived = hashlib.sha256(key_material).digest()
    fernet_key = base64.urlsafe_b64encode(derived)
    _fernet = Fernet(fernet_key)
    return _fernet


def encrypt(plaintext: str) -> str:
    """
    Encrypt a string and return a base64-encoded ciphertext.

    The ciphertext is prefixed with 'enc:' to distinguish encrypted
    values from plaintext (allows gradual migration).
    """
    if not plaintext:
        return plaintext

    f = _get_fernet()
    ciphertext = f.encrypt(plaintext.encode("utf-8"))
    return "enc:" + ciphertext.decode("utf-8")


def decrypt(ciphertext: str) -> str:
    """
    Decrypt a value. Handles both encrypted ('enc:...') and plaintext values
    for backward compatibility during migration.
    """
    if not ciphertext:
        return ciphertext

    # Plain text (not yet migrated) — return as-is
    if not ciphertext.startswith("enc:"):
        return ciphertext

    f = _get_fernet()
    try:
        payload = ciphertext[4:]  # Remove 'enc:' prefix
        plaintext = f.decrypt(payload.encode("utf-8"))
        return plaintext.decode("utf-8")
    except Exception as e:
        logger.warning("Failed to decrypt value — returning raw", error=str(e))
        return ciphertext


def is_encrypted(value: str) -> bool:
    """Check if a value is encrypted (has the 'enc:' prefix)."""
    return bool(value) and value.startswith("enc:")