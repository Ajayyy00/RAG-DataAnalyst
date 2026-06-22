"""Add providers.provider_type discriminator (physician | nurse | other).

The synthetic dataset models a real clinical workforce — physicians and nurses
are distinct populations with very different headcounts and analytics. This
additive, nullable column lets the copilot answer questions like
"how many nurses work in the ICU" without changing any existing behaviour.

Backfill heuristic: rows whose specialty looks like a nursing role are tagged
'nurse'; everything else with a specialty is tagged 'physician'. New data sets
the column explicitly.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "providers",
        sa.Column("provider_type", sa.String(length=20), nullable=True),
    )
    op.create_index(
        "ix_providers_provider_type", "providers", ["provider_type"], unique=False
    )

    # Best-effort backfill of any pre-existing rows.
    op.execute(
        """
        UPDATE providers
        SET provider_type = CASE
            WHEN specialty ILIKE '%nurse%'
              OR specialty ILIKE '%nursing%'
              OR specialty ILIKE '%CNA%'
              OR specialty ILIKE '%LPN%'
              OR specialty ILIKE '%RN%' THEN 'nurse'
            WHEN specialty IS NOT NULL THEN 'physician'
            ELSE NULL
        END
        WHERE provider_type IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_providers_provider_type", table_name="providers")
    op.drop_column("providers", "provider_type")
