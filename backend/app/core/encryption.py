"""PHI encryption-at-rest: key management + Fernet cipher abstraction.

Design
------
* ``KeyProvider`` is the pluggable key-management seam. The default
  ``EnvKeyProvider`` reads keys from ``PHI_ENCRYPTION_KEYS`` (comma-separated,
  newest first). Swap in a KMS/Vault provider in production by setting
  ``set_key_provider(...)`` at startup — no call sites change.
* Encryption uses Fernet (AES-128-CBC + HMAC-SHA256, authenticated). Multiple
  keys are wrapped in a ``MultiFernet`` so the FIRST key encrypts while ALL keys
  can decrypt — enabling zero-downtime key rotation.
* When no key is configured the cipher is a no-op pass-through, so development
  without a key still works and existing plaintext rows are never corrupted.
"""

from __future__ import annotations

from typing import List, Optional, Protocol

import structlog
from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# Marker prefix so we can tell ciphertext from legacy plaintext on read.
_ENC_PREFIX = "enc::"


class KeyProvider(Protocol):
    """Supplies Fernet keys (urlsafe base64, 32 bytes). Newest key first."""

    def get_keys(self) -> List[bytes]:  # pragma: no cover - interface
        ...


class EnvKeyProvider:
    """Reads keys from settings.phi_encryption_keys (comma-separated)."""

    def get_keys(self) -> List[bytes]:
        raw = settings.phi_encryption_keys
        if not raw:
            return []
        return [k.strip().encode() for k in raw.split(",") if k.strip()]


_provider: KeyProvider = EnvKeyProvider()
_cipher: Optional[MultiFernet] = None
_cipher_built = False


def set_key_provider(provider: KeyProvider) -> None:
    """Override the key provider (e.g. a KMS/Vault-backed one) and reset cache."""
    global _provider, _cipher, _cipher_built
    _provider = provider
    _cipher = None
    _cipher_built = False


def _get_cipher() -> Optional[MultiFernet]:
    global _cipher, _cipher_built
    if not _cipher_built:
        keys = _provider.get_keys()
        if keys:
            try:
                _cipher = MultiFernet([Fernet(k) for k in keys])
            except Exception as exc:  # malformed key — fail loudly, don't silently skip
                raise RuntimeError(f"Invalid PHI_ENCRYPTION_KEYS: {exc}") from exc
        else:
            _cipher = None
            if settings.is_production:
                logger.warning(
                    "PHI encryption is DISABLED (no PHI_ENCRYPTION_KEYS set in production)"
                )
        _cipher_built = True
    return _cipher


def encryption_enabled() -> bool:
    return _get_cipher() is not None


def encrypt_str(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a string; returns a prefixed token. No-op when disabled or None."""
    if plaintext is None:
        return None
    cipher = _get_cipher()
    if cipher is None:
        return plaintext
    token = cipher.encrypt(plaintext.encode("utf-8")).decode("ascii")
    return f"{_ENC_PREFIX}{token}"


def decrypt_str(value: Optional[str]) -> Optional[str]:
    """Decrypt a stored value. Legacy/plaintext values pass through unchanged."""
    if value is None:
        return None
    if not value.startswith(_ENC_PREFIX):
        # Legacy plaintext written before encryption was enabled.
        return value
    cipher = _get_cipher()
    if cipher is None:
        # Encrypted data but no key available — surface clearly, don't crash read.
        logger.error("Encountered encrypted PHI but no decryption key is configured")
        return None
    token = value[len(_ENC_PREFIX) :].encode("ascii")
    try:
        return cipher.decrypt(token).decode("utf-8")
    except InvalidToken:
        logger.error("PHI decryption failed (key rotation issue?)")
        return None
