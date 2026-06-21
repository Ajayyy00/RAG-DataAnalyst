"""Widen users.first_name/last_name to TEXT for encrypted PHI at rest.

Fernet ciphertext is much longer than the source plaintext, so the columns are
converted from VARCHAR(100) to TEXT. The EncryptedString type writes ciphertext
on save; legacy plaintext rows decrypt as pass-through until re-encrypted by
app/scripts/reencrypt_pii.py.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "first_name", type_=sa.Text(), existing_nullable=True)
    op.alter_column("users", "last_name", type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    # NOTE: decrypt PHI BEFORE downgrading or VARCHAR(100) may truncate ciphertext.
    op.alter_column(
        "users", "first_name", type_=sa.String(length=100), existing_nullable=True
    )
    op.alter_column(
        "users", "last_name", type_=sa.String(length=100), existing_nullable=True
    )
