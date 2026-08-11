"""add source column to things table

Revision ID: 0007_add_thing_source
Revises: 0006_virtual_thing_shared_state
Create Date: 2026-07-23 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_add_thing_source"
down_revision = "0006_virtual_thing_shared_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "things",
        sa.Column(
            "source",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("things", "source")