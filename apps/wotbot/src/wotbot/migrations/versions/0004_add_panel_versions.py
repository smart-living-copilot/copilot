"""add panel versions

Revision ID: 0004_add_panel_versions
Revises: 0003_add_panels
Create Date: 2026-06-05 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_add_panel_versions"
down_revision = "0003_add_panels"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "panel_versions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("panel_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("html", sa.Text(), nullable=False),
        sa.Column(
            "capabilities",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["panel_id"], ["panels.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "panel_id",
            "version",
            name="uq_panel_versions_panel_version",
        ),
        if_not_exists=True,
    )
    op.create_index(
        "ix_panel_versions_panel_id",
        "panel_versions",
        ["panel_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_panel_versions_panel_id_created_at",
        "panel_versions",
        ["panel_id", "created_at"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_panel_versions_panel_id_created_at",
        table_name="panel_versions",
        if_exists=True,
    )
    op.drop_index(
        "ix_panel_versions_panel_id",
        table_name="panel_versions",
        if_exists=True,
    )
    op.drop_table("panel_versions", if_exists=True)
