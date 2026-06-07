"""baseline application schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-02 00:00:00
"""

from __future__ import annotations

import os

from alembic import op
from pgvector.sqlalchemy import VECTOR
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _vector_dimensions() -> int:
    raw_value = os.getenv("SEARCH_VECTOR_DIMENSIONS", "1024")
    try:
        value = int(raw_value)
    except ValueError:
        return 1024
    return value if value > 0 else 1024


def upgrade() -> None:
    vector_dimensions = _vector_dimensions()

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("key_prefix", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "scopes",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("user_id", sa.Text(), nullable=False),
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
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.UniqueConstraint("key_hash"),
        if_not_exists=True,
    )
    op.create_index(
        "ix_api_keys_key_hash",
        "api_keys",
        ["key_hash"],
        if_not_exists=True,
    )

    op.create_table(
        "things",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "tags",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("document", postgresql.JSONB(), nullable=False),
        sa.Column("document_hash", sa.Text(), nullable=False),
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
        "thing_credentials",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("thing_id", sa.Text(), nullable=False),
        sa.Column("security_name", sa.Text(), nullable=False),
        sa.Column("scheme", sa.Text(), nullable=False),
        sa.Column("credentials", postgresql.JSONB(), nullable=False),
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
        sa.UniqueConstraint("thing_id", "security_name", name="uq_thing_security"),
        if_not_exists=True,
    )

    op.create_table(
        "thing_event_outbox",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("thing_id", sa.Text(), nullable=False),
        sa.Column(
            "event_hash",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        if_not_exists=True,
    )
    op.create_index(
        "idx_thing_event_outbox_pending",
        "thing_event_outbox",
        ["published_at", "id"],
        if_not_exists=True,
    )

    op.create_table(
        "threads",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column(
            "kind",
            sa.String(),
            nullable=False,
            server_default=sa.text("'chat'"),
        ),
        sa.Column(
            "visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("job_id", sa.String()),
        sa.CheckConstraint("kind IN ('chat', 'job')", name="ck_threads_kind"),
        if_not_exists=True,
    )
    op.create_index(
        "idx_threads_updated_at",
        "threads",
        ["updated_at", "created_at"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_threads_visible_kind",
        "threads",
        ["kind", "visible", "updated_at"],
        if_not_exists=True,
    )

    op.create_table(
        "search_index_chunks",
        sa.Column("chunk_id", sa.Text(), primary_key=True),
        sa.Column("thing_id", sa.Text(), nullable=False),
        sa.Column("page_content", sa.Text(), nullable=False),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("embedding", VECTOR(vector_dimensions), nullable=False),
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
    op.create_index(
        "idx_search_index_chunks_thing_id",
        "search_index_chunks",
        ["thing_id"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_search_index_chunks_embedding_hnsw",
        "search_index_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
        if_not_exists=True,
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_from_thread_id", sa.Text(), nullable=False),
        sa.Column("job_thread_id", sa.Text(), nullable=False),
        sa.Column(
            "action_kind",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'prompt'"),
        ),
        sa.Column(
            "interaction_mode",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'autonomous'"),
        ),
        sa.Column(
            "output_kind",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'narrative'"),
        ),
        sa.Column("action", postgresql.JSONB(), nullable=False),
        sa.Column("trigger", postgresql.JSONB(), nullable=False),
        sa.Column("output", postgresql.JSONB(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("trigger_kind", sa.Text(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("subscription_id", sa.Text()),
        sa.Column("resource_health", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_id", sa.Text()),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_status", sa.Text()),
        sa.Column("last_error", sa.Text()),
        sa.Column("last_response", sa.Text()),
        sa.Column(
            "run_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("active_run_id", sa.Text()),
        sa.Column("active_run_started_at", sa.DateTime(timezone=True)),
        sa.Column("active_run_source", sa.Text()),
        sa.Column("waiting_question", sa.Text()),
        sa.CheckConstraint(
            "action_kind IN ('prompt', 'analysis')",
            name="ck_jobs_action_kind",
        ),
        sa.CheckConstraint(
            "trigger_kind IN ('time', 'event')",
            name="ck_jobs_trigger_kind",
        ),
        sa.CheckConstraint(
            "interaction_mode IN ('autonomous', 'required_checkin')",
            name="ck_jobs_interaction_mode",
        ),
        sa.CheckConstraint(
            "output_kind IN ('narrative', 'structured_record')",
            name="ck_jobs_output_kind",
        ),
        sa.CheckConstraint(
            "(\"action\" ->> 'kind') = action_kind",
            name="ck_jobs_action_json_kind",
        ),
        sa.CheckConstraint(
            "(\"trigger\" ->> 'kind') = trigger_kind",
            name="ck_jobs_trigger_json_kind",
        ),
        sa.CheckConstraint(
            "(\"output\" ->> 'kind') = output_kind",
            name="ck_jobs_output_json_kind",
        ),
        sa.CheckConstraint(
            "last_run_status IS NULL OR last_run_status IN ("
            "'running', 'succeeded', 'failed', 'waiting_for_input', "
            "'cancelled', 'skipped')",
            name="ck_jobs_last_run_status",
        ),
        sa.CheckConstraint(
            "active_run_source IS NULL OR active_run_source IN ('manual', 'time', 'event')",
            name="ck_jobs_active_run_source",
        ),
        sa.UniqueConstraint("job_thread_id"),
        if_not_exists=True,
    )
    op.create_index(
        "idx_jobs_due",
        "jobs",
        ["trigger_kind", "enabled", "next_run_at"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_jobs_created_from_thread",
        "jobs",
        ["created_from_thread_id"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_jobs_subscription",
        "jobs",
        ["subscription_id", "enabled"],
        if_not_exists=True,
    )

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "job_id",
            sa.Text(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_thread_id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "trigger_payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column("response_text", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('manual', 'time', 'event')",
            name="ck_job_runs_source",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'running', 'succeeded', 'failed', 'waiting_for_input', "
            "'cancelled', 'skipped')",
            name="ck_job_runs_status",
        ),
        if_not_exists=True,
    )
    op.create_index(
        "idx_job_runs_job_started",
        "job_runs",
        ["job_id", "started_at"],
        if_not_exists=True,
    )

    op.create_table(
        "job_run_events",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            primary_key=True,
        ),
        sa.Column(
            "job_id",
            sa.Text(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            sa.Text(),
            sa.ForeignKey("job_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("payload", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ("
            "'run_started', 'user_reply', 'waiting_for_input', "
            "'assistant_message', 'record_submitted', 'run_succeeded', "
            "'run_failed', 'run_cancelled', 'run_skipped')",
            name="ck_job_run_events_type",
        ),
        if_not_exists=True,
    )
    op.create_index(
        "idx_job_run_events_job_created",
        "job_run_events",
        ["job_id", "created_at", "id"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_job_run_events_run_created",
        "job_run_events",
        ["run_id", "created_at", "id"],
        if_not_exists=True,
    )

    op.create_table(
        "virtual_record_things",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "source_job_id",
            sa.Text(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "schema_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("record_schema", postgresql.JSONB(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "description",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
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
        "virtual_records",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "thing_id",
            sa.Text(),
            sa.ForeignKey("virtual_record_things.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column(
            "source_job_id",
            sa.Text(),
            sa.ForeignKey("jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_run_id", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("raw_input", sa.Text()),
        sa.Column("confidence", sa.Float()),
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
        sa.UniqueConstraint(
            "thing_id",
            "source_run_id",
            name="uq_virtual_records_run",
        ),
        if_not_exists=True,
    )
    op.create_index(
        "idx_virtual_records_thing_recorded",
        "virtual_records",
        ["thing_id", "recorded_at"],
        if_not_exists=True,
    )
    op.create_index(
        "idx_virtual_records_source_run",
        "virtual_records",
        ["source_run_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_virtual_records_source_run",
        table_name="virtual_records",
        if_exists=True,
    )
    op.drop_index(
        "idx_virtual_records_thing_recorded",
        table_name="virtual_records",
        if_exists=True,
    )
    op.drop_table("virtual_records", if_exists=True)
    op.drop_table("virtual_record_things", if_exists=True)
    op.drop_index(
        "idx_job_run_events_run_created",
        table_name="job_run_events",
        if_exists=True,
    )
    op.drop_index(
        "idx_job_run_events_job_created",
        table_name="job_run_events",
        if_exists=True,
    )
    op.drop_table("job_run_events", if_exists=True)
    op.drop_index(
        "idx_job_runs_job_started",
        table_name="job_runs",
        if_exists=True,
    )
    op.drop_table("job_runs", if_exists=True)
    op.drop_index("idx_jobs_subscription", table_name="jobs", if_exists=True)
    op.drop_index("idx_jobs_created_from_thread", table_name="jobs", if_exists=True)
    op.drop_index("idx_jobs_due", table_name="jobs", if_exists=True)
    op.drop_table("jobs", if_exists=True)
    op.drop_index(
        "idx_search_index_chunks_embedding_hnsw",
        table_name="search_index_chunks",
        if_exists=True,
    )
    op.drop_index(
        "idx_search_index_chunks_thing_id",
        table_name="search_index_chunks",
        if_exists=True,
    )
    op.drop_table("search_index_chunks", if_exists=True)
    op.drop_index("idx_threads_visible_kind", table_name="threads", if_exists=True)
    op.drop_index("idx_threads_updated_at", table_name="threads", if_exists=True)
    op.drop_table("threads", if_exists=True)
    op.drop_index(
        "idx_thing_event_outbox_pending",
        table_name="thing_event_outbox",
        if_exists=True,
    )
    op.drop_table("thing_event_outbox", if_exists=True)
    op.drop_table("thing_credentials", if_exists=True)
    op.drop_table("things", if_exists=True)
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys", if_exists=True)
    op.drop_table("api_keys", if_exists=True)
