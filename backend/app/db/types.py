"""Custom SQLAlchemy column types.

``EncryptedString`` transparently encrypts on write and decrypts on read using
the Fernet cipher in :mod:`app.core.encryption`. It is a drop-in replacement for
``String``/``Text`` columns that hold PHI accessed via the ORM.

IMPORTANT: ciphertext is non-deterministic, so columns encrypted this way cannot
be used for SQL equality/range filters or joins. Apply it only to columns that
are NOT filtered/joined by the analytics SQL path (e.g. the ``users`` table,
which the read-only executor cannot access at all).
"""

from __future__ import annotations

from sqlalchemy import Text
from sqlalchemy.types import TypeDecorator

from app.core.encryption import decrypt_str, encrypt_str


class EncryptedString(TypeDecorator):
    """Application-layer encrypted string. Stored as TEXT (base64 ciphertext)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # write path
        return encrypt_str(value)

    def process_result_value(self, value, dialect):  # read path
        return decrypt_str(value)
