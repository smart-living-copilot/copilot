"""add cron schedules to jobs

Revision ID: 0002_add_job_cron_schedule
Revises: 0001_baseline
Create Date: 2026-06-02 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_add_job_cron_schedule"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("cron_expression", sa.Text()),
        if_not_exists=True,
    )
    op.add_column(
        "jobs",
        sa.Column("cron_timezone", sa.Text()),
        if_not_exists=True,
    )
    op.execute("ALTER TABLE jobs DROP CONSTRAINT IF EXISTS ck_jobs_schedule_kind")
    op.create_check_constraint(
        "ck_jobs_schedule_kind",
        "jobs",
        "schedule_kind IS NULL OR schedule_kind IN ('once', 'interval', 'cron')",
    )


def downgrade() -> None:
    op.execute("ALTER TABLE jobs DROP CONSTRAINT IF EXISTS ck_jobs_schedule_kind")
    op.create_check_constraint(
        "ck_jobs_schedule_kind",
        "jobs",
        "schedule_kind IS NULL OR schedule_kind IN ('once', 'interval')",
    )
    op.drop_column("jobs", "cron_timezone", if_exists=True)
    op.drop_column("jobs", "cron_expression", if_exists=True)
