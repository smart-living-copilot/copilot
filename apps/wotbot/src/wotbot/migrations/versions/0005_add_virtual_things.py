"""add virtual things

Revision ID: 0005_add_virtual_things
Revises: 0004_add_panel_versions
Create Date: 2026-06-11 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_add_virtual_things"
down_revision = "0004_add_panel_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "virtual_things",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_thread_id", sa.Text()),
        sa.Column("abstract_td", JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        if_not_exists=True,
    )
    op.create_table(
        "virtual_thing_bindings",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("thing_id", sa.Text(), nullable=False),
        sa.Column("affordance_type", sa.Text(), nullable=False),
        sa.Column("affordance_name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("handler_code", sa.Text()),
        sa.Column(
            "config",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "capabilities",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("trigger", JSONB()),
        sa.Column("state", JSONB()),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("cache_ttl_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["thing_id"], ["virtual_things.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "thing_id",
            "affordance_type",
            "affordance_name",
            name="uq_virtual_thing_binding_affordance",
        ),
        if_not_exists=True,
    )
    op.create_index(
        "idx_virtual_thing_bindings_thing",
        "virtual_thing_bindings",
        ["thing_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_virtual_thing_bindings_thing",
        table_name="virtual_thing_bindings",
        if_exists=True,
    )
    op.drop_table("virtual_thing_bindings", if_exists=True)
    op.drop_table("virtual_things", if_exists=True)
