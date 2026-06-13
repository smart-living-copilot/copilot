"""add virtual thing shared state

Revision ID: 0006_virtual_thing_shared_state
Revises: 0005_add_virtual_things
Create Date: 2026-06-13 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_virtual_thing_shared_state"
down_revision = "0005_add_virtual_things"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "virtual_things",
        sa.Column(
            "shared_state",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "virtual_things",
        sa.Column(
            "shared_state_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )


def downgrade() -> None:
    op.drop_column("virtual_things", "shared_state_version")
    op.drop_column("virtual_things", "shared_state")
