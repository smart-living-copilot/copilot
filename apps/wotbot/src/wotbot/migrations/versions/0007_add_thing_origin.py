"""add discovery sources and resource origin metadata

Revision ID: 0007_add_thing_origin
Revises: 0006_virtual_thing_shared_state
Create Date: 2026-07-23 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_add_thing_origin"
down_revision = "0006_virtual_thing_shared_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_sources",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "tags",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("network_access", sa.Text(), nullable=False, server_default="public"),
        sa.Column("security_name", sa.Text(), nullable=False, server_default="source_sc"),
        sa.Column("security_scheme", sa.Text(), nullable=False, server_default="nosec"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_id", name="uq_discovery_source_identity"),
    )
    op.create_table(
        "discovery_source_credentials",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("security_name", sa.Text(), nullable=False),
        sa.Column("scheme", sa.Text(), nullable=False),
        sa.Column("credentials", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_id"], ["discovery_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "security_name", name="uq_source_security"),
    )

    op.add_column(
        "things",
        sa.Column("origin_kind", sa.Text(), nullable=False, server_default=sa.text("'manual'")),
    )
    op.add_column("things", sa.Column("origin_provider", sa.Text(), nullable=True))
    op.add_column("things", sa.Column("origin_external_id", sa.Text(), nullable=True))
    op.add_column("things", sa.Column("origin_source_id", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_things_origin_source",
        "things",
        "discovery_sources",
        ["origin_source_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_things_origin_shape",
        "things",
        "(origin_kind = 'manual' AND origin_provider IS NULL "
        "AND origin_external_id IS NULL AND origin_source_id IS NULL) OR "
        "(origin_kind = 'discovery' AND origin_provider IS NOT NULL "
        "AND origin_external_id IS NOT NULL AND origin_source_id IS NOT NULL)",
    )
    op.create_index(
        "uq_things_discovery_resource_origin",
        "things",
        ["origin_source_id", "origin_provider", "origin_external_id"],
        unique=True,
        postgresql_where=sa.text("origin_kind = 'discovery'"),
    )


def downgrade() -> None:
    op.drop_index("uq_things_discovery_resource_origin", table_name="things")
    op.drop_constraint("ck_things_origin_shape", "things", type_="check")
    op.drop_constraint("fk_things_origin_source", "things", type_="foreignkey")
    op.drop_column("things", "origin_source_id")
    op.drop_column("things", "origin_external_id")
    op.drop_column("things", "origin_provider")
    op.drop_column("things", "origin_kind")
    op.drop_table("discovery_source_credentials")
    op.drop_table("discovery_sources")
