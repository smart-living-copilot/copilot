from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from copilot.core.orm import Base


class VirtualRecordThing(Base):
    __tablename__ = "virtual_record_things"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_job_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    record_schema: Mapped[Any] = mapped_column(JSONB, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class VirtualRecord(Base):
    __tablename__ = "virtual_records"
    __table_args__ = (
        UniqueConstraint("thing_id", "source_run_id", name="uq_virtual_records_run"),
        Index("idx_virtual_records_thing_recorded", "thing_id", "recorded_at"),
        Index("idx_virtual_records_source_run", "source_run_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    thing_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("virtual_record_things.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_job_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_run_id: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data: Mapped[Any] = mapped_column(JSONB, nullable=False)
    raw_input: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
