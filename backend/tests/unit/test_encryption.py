"""Unit tests for PHI encryption at rest."""

import pytest
from cryptography.fernet import Fernet

import app.core.encryption as enc


@pytest.fixture
def with_key(monkeypatch):
    """Enable encryption with a fresh key for the duration of a test."""
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(enc.settings, "phi_encryption_keys", key, raising=False)
    enc.set_key_provider(enc.EnvKeyProvider())  # reset cipher cache
    yield key
    monkeypatch.setattr(enc.settings, "phi_encryption_keys", None, raising=False)
    enc.set_key_provider(enc.EnvKeyProvider())


def test_roundtrip_with_key(with_key):
    assert enc.encryption_enabled() is True
    ct = enc.encrypt_str("Jane Doe")
    assert ct != "Jane Doe"
    assert ct.startswith("enc::")
    assert enc.decrypt_str(ct) == "Jane Doe"


def test_none_passthrough(with_key):
    assert enc.encrypt_str(None) is None
    assert enc.decrypt_str(None) is None


def test_legacy_plaintext_passthrough(with_key):
    # A value written before encryption was enabled has no prefix → returned as-is.
    assert enc.decrypt_str("legacy plaintext") == "legacy plaintext"


def test_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(enc.settings, "phi_encryption_keys", None, raising=False)
    enc.set_key_provider(enc.EnvKeyProvider())
    assert enc.encryption_enabled() is False
    assert enc.encrypt_str("secret") == "secret"  # passthrough, no corruption
    assert enc.decrypt_str("secret") == "secret"


def test_key_rotation_old_key_still_decrypts(monkeypatch):
    old = Fernet.generate_key().decode()
    new = Fernet.generate_key().decode()
    # Encrypt under the old key only.
    monkeypatch.setattr(enc.settings, "phi_encryption_keys", old, raising=False)
    enc.set_key_provider(enc.EnvKeyProvider())
    ct = enc.encrypt_str("rotate me")
    # Now rotate: new key first, old key retained for decryption.
    monkeypatch.setattr(
        enc.settings, "phi_encryption_keys", f"{new},{old}", raising=False
    )
    enc.set_key_provider(enc.EnvKeyProvider())
    assert enc.decrypt_str(ct) == "rotate me"
    # Cleanup
    monkeypatch.setattr(enc.settings, "phi_encryption_keys", None, raising=False)
    enc.set_key_provider(enc.EnvKeyProvider())
