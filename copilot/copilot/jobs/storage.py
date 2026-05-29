from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Index, Integer, Text, create_engine, inspect, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from copilot.jobs.models import CreateJobRequest, Job


class JobStorageBase(DeclarativeBase):
    pass


class JobRecord(JobStorageBase):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("idx_jobs_due", "trigger_type", "enabled", "next_run_at"),
        Index("idx_jobs_subscription", "subscription_id", "enabled"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    thread_id: Mapped[str] = mapped_column(Text, nullable=False)
    job_type: Mapped[str] = mapped_column(Text, nullable=False, default="prompt")
    prompt: Mapped[str | None] = mapped_column(Text)
    analysis_code: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_type: Mapped[str] = mapped_column(Text, nullable=False)
    run_at: Mapped[str | None] = mapped_column(Text)
    interval_seconds: Mapped[int | None] = mapped_column(Integer)
    next_run_at: Mapped[str | None] = mapped_column(Text)
    thing_id: Mapped[str | None] = mapped_column(Text)
    event_name: Mapped[str | None] = mapped_column(Text)
    subscription_id: Mapped[str | None] = mapped_column(Text)
    subscription_input_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
    last_run_at: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_response: Mapped[str | None] = mapped_column(Text)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_fetch_value: Mapped[str | None] = mapped_column(Text)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def dt_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def iso_to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _sqlite_engine_config(db_path: str) -> tuple[str, dict[str, Any]]:
    connect_args: dict[str, Any] = {"check_same_thread": False}
    if db_path == ":memory:":
        return "sqlite://", {"connect_args": connect_args, "poolclass": StaticPool}
    if db_path.startswith("sqlite:"):
        return db_path, {"connect_args": connect_args}

    path = Path(db_path).expanduser()
    if path.parent != Path("."):
        path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}", {"connect_args": connect_args}


def _create_engine(db_path: str) -> Engine:
    url, kwargs = _sqlite_engine_config(db_path)
    return create_engine(url, future=True, **kwargs)


def record_to_job(record: JobRecord) -> Job:
    return Job(
        id=record.id,
        name=record.name,
        thread_id=record.thread_id,
        job_type=record.job_type,
        prompt=record.prompt,
        analysis_code=record.analysis_code,
        enabled=bool(record.enabled),
        trigger_type=record.trigger_type,
        run_at=iso_to_dt(record.run_at),
        interval_seconds=record.interval_seconds,
        next_run_at=iso_to_dt(record.next_run_at),
        thing_id=record.thing_id,
        event_name=record.event_name,
        subscription_id=record.subscription_id,
        subscription_input=json.loads(record.subscription_input_json)
        if record.subscription_input_json
        else None,
        created_at=iso_to_dt(record.created_at) or utc_now(),
        updated_at=iso_to_dt(record.updated_at) or utc_now(),
        last_run_at=iso_to_dt(record.last_run_at),
        last_error=record.last_error,
        last_response=record.last_response,
        run_count=int(record.run_count or 0),
        last_fetch_value=record.last_fetch_value,
    )


class JobRepository:
    def __init__(self, db_path: str) -> None:
        self._engine = _create_engine(db_path)
        self._session_factory = sessionmaker(
            bind=self._engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        JobStorageBase.metadata.create_all(self._engine)

        with self._engine.begin() as conn:
            columns = {column["name"] for column in inspect(conn).get_columns("jobs")}
            if "job_type" not in columns:
                conn.execute(
                    text("ALTER TABLE jobs ADD COLUMN job_type TEXT NOT NULL DEFAULT 'prompt'")
                )
            if "analysis_code" not in columns:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN analysis_code TEXT"))
            if "last_response" not in columns:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN last_response TEXT"))
            if "run_count" not in columns:
                conn.execute(
                    text("ALTER TABLE jobs ADD COLUMN run_count INTEGER NOT NULL DEFAULT 0")
                )
            if "last_fetch_value" not in columns:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN last_fetch_value TEXT"))
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_jobs_due "
                    "ON jobs(trigger_type, enabled, next_run_at)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS idx_jobs_subscription "
                    "ON jobs(subscription_id, enabled)"
                )
            )

    async def create_job(
        self,
        request: CreateJobRequest,
        *,
        next_run_at: datetime | None,
        subscription_id: str | None,
    ) -> Job:
        return await asyncio.to_thread(
            self._create_job_sync,
            request,
            next_run_at,
            subscription_id,
        )

    def _create_job_sync(
        self,
        request: CreateJobRequest,
        next_run_at: datetime | None,
        subscription_id: str | None,
    ) -> Job:
        now = utc_now()
        job_id = str(uuid4())
        record = JobRecord(
            id=job_id,
            name=request.name,
            thread_id=request.thread_id,
            job_type=request.job_type,
            prompt=request.prompt or "",
            analysis_code=request.analysis_code,
            enabled=1,
            trigger_type=request.trigger_type,
            run_at=dt_to_iso(request.run_at),
            interval_seconds=request.interval_seconds,
            next_run_at=dt_to_iso(next_run_at),
            thing_id=request.thing_id,
            event_name=request.event_name,
            subscription_id=subscription_id,
            subscription_input_json=(
                json.dumps(request.subscription_input)
                if request.subscription_input is not None
                else None
            ),
            created_at=dt_to_iso(now) or "",
            updated_at=dt_to_iso(now) or "",
            last_run_at=None,
            last_error=None,
            last_response=None,
            run_count=0,
            last_fetch_value=None,
        )
        with self._session_factory() as session:
            session.add(record)
            session.commit()
            return record_to_job(record)

    def _get_record(self, job_id: str) -> JobRecord:
        with self._session_factory() as session:
            record = session.get(JobRecord, job_id)
            if record is None:
                raise KeyError(job_id)
            return record

    async def get_job(self, job_id: str) -> Job:
        return await asyncio.to_thread(self._get_job_sync, job_id)

    def _get_job_sync(self, job_id: str) -> Job:
        return record_to_job(self._get_record(job_id))

    async def list_jobs(self, thread_id: str | None = None) -> list[Job]:
        return await asyncio.to_thread(self._list_jobs_sync, thread_id)

    def _list_jobs_sync(self, thread_id: str | None = None) -> list[Job]:
        statement = select(JobRecord)
        if thread_id:
            statement = statement.where(JobRecord.thread_id == thread_id)
        statement = statement.order_by(JobRecord.created_at.desc())

        with self._session_factory() as session:
            records = session.scalars(statement).all()
            return [record_to_job(record) for record in records]

    async def delete_job(self, job_id: str) -> Job:
        return await asyncio.to_thread(self._delete_job_sync, job_id)

    def _delete_job_sync(self, job_id: str) -> Job:
        with self._session_factory() as session:
            record = session.get(JobRecord, job_id)
            if record is None:
                raise KeyError(job_id)
            job = record_to_job(record)
            session.delete(record)
            session.commit()
            return job

    async def list_due_time_jobs(self, *, now: datetime) -> list[Job]:
        return await asyncio.to_thread(self._list_due_time_jobs_sync, now)

    def _list_due_time_jobs_sync(self, now: datetime) -> list[Job]:
        statement = (
            select(JobRecord)
            .where(
                JobRecord.trigger_type == "time",
                JobRecord.enabled == 1,
                JobRecord.next_run_at.is_not(None),
                JobRecord.next_run_at <= dt_to_iso(now),
            )
            .order_by(JobRecord.next_run_at.asc())
        )

        with self._session_factory() as session:
            records = session.scalars(statement).all()
            return [record_to_job(record) for record in records]

    async def list_event_jobs_for_subscription(self, subscription_id: str) -> list[Job]:
        return await asyncio.to_thread(
            self._list_event_jobs_for_subscription_sync,
            subscription_id,
        )

    def _list_event_jobs_for_subscription_sync(self, subscription_id: str) -> list[Job]:
        statement = select(JobRecord).where(
            JobRecord.trigger_type == "event",
            JobRecord.enabled == 1,
            JobRecord.subscription_id == subscription_id,
        )

        with self._session_factory() as session:
            records = session.scalars(statement).all()
            return [record_to_job(record) for record in records]

    async def list_enabled_event_jobs(self) -> list[Job]:
        return await asyncio.to_thread(self._list_enabled_event_jobs_sync)

    def _list_enabled_event_jobs_sync(self) -> list[Job]:
        statement = select(JobRecord).where(
            JobRecord.trigger_type == "event",
            JobRecord.enabled == 1,
        )

        with self._session_factory() as session:
            records = session.scalars(statement).all()
            return [record_to_job(record) for record in records]

    async def set_subscription_id(self, job_id: str, subscription_id: str | None) -> None:
        await asyncio.to_thread(self._set_subscription_id_sync, job_id, subscription_id)

    def _set_subscription_id_sync(self, job_id: str, subscription_id: str | None) -> None:
        now = utc_now()
        with self._session_factory() as session:
            session.execute(
                update(JobRecord)
                .where(JobRecord.id == job_id)
                .values(subscription_id=subscription_id, updated_at=dt_to_iso(now))
            )
            session.commit()

    async def mark_time_job_result(
        self,
        *,
        job: Job,
        now: datetime,
        success: bool,
        error: str | None,
        response_text: str | None,
        last_fetch_value: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._mark_time_job_result_sync,
            job,
            now,
            success,
            error,
            response_text,
            last_fetch_value,
        )

    def _mark_time_job_result_sync(
        self,
        job: Job,
        now: datetime,
        success: bool,
        error: str | None,
        response_text: str | None,
        last_fetch_value: str | None = None,
    ) -> None:
        next_run_at: datetime | None
        enabled = job.enabled

        if job.interval_seconds:
            next_run_at = now + timedelta(seconds=job.interval_seconds)
        else:
            next_run_at = None
            enabled = False

        values: dict[str, Any] = {
            "next_run_at": dt_to_iso(next_run_at),
            "enabled": 1 if enabled else 0,
            "last_run_at": dt_to_iso(now),
            "last_error": None if success else error,
            "last_response": response_text if success else None,
            "run_count": JobRecord.run_count + 1,
            "updated_at": dt_to_iso(now),
        }
        if last_fetch_value is not None:
            values["last_fetch_value"] = last_fetch_value

        with self._session_factory() as session:
            session.execute(
                update(JobRecord).where(JobRecord.id == job.id).values(**values)
            )
            session.commit()

    async def mark_event_job_result(
        self,
        *,
        job_id: str,
        now: datetime,
        success: bool,
        error: str | None,
        response_text: str | None,
        last_fetch_value: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._mark_job_result_sync,
            job_id=job_id,
            now=now,
            success=success,
            error=error,
            response_text=response_text,
            last_fetch_value=last_fetch_value,
        )

    async def mark_manual_job_result(
        self,
        *,
        job_id: str,
        now: datetime,
        success: bool,
        error: str | None,
        response_text: str | None,
        last_fetch_value: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._mark_job_result_sync,
            job_id=job_id,
            now=now,
            success=success,
            error=error,
            response_text=response_text,
            last_fetch_value=last_fetch_value,
        )

    def _mark_job_result_sync(
        self,
        *,
        job_id: str,
        now: datetime,
        success: bool,
        error: str | None,
        response_text: str | None,
        last_fetch_value: str | None,
    ) -> None:
        values: dict[str, Any] = {
            "last_run_at": dt_to_iso(now),
            "last_error": None if success else error,
            "last_response": response_text if success else None,
            "run_count": JobRecord.run_count + 1,
            "updated_at": dt_to_iso(now),
        }
        if last_fetch_value is not None:
            values["last_fetch_value"] = last_fetch_value

        with self._session_factory() as session:
            session.execute(
                update(JobRecord).where(JobRecord.id == job_id).values(**values)
            )
            session.commit()
