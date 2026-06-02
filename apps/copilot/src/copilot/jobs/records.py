from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from jsonschema import Draft202012Validator, SchemaError, ValidationError
from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from copilot.catalog.events import build_change_event, build_remove_event
from copilot.catalog.events.outbox import enqueue_thing_event
from copilot.catalog.store import delete_thing, put_thing
from copilot.catalog.validation import validate_document
from copilot.core.database import get_session_factory
from copilot.core.orm import Base
from copilot.jobs.store import _json_safe, iso, utc_now

VIRTUAL_RECORD_THING_PREFIX = "virtual:records:"


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


def is_virtual_record_thing_id(thing_id: str | None) -> bool:
    return isinstance(thing_id, str) and thing_id.startswith(VIRTUAL_RECORD_THING_PREFIX)


def make_virtual_record_thing_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "record-job"
    return f"{VIRTUAL_RECORD_THING_PREFIX}{slug}-{uuid4().hex[:8]}"


def validate_record_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        raise ValueError("structured record jobs require record_schema to be an object")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"invalid record_schema: {exc.message}") from exc
    if schema.get("type") != "object":
        raise ValueError("record_schema must be a JSON Schema object with type='object'")
    properties = schema.get("properties")
    if properties is not None and not isinstance(properties, dict):
        raise ValueError("record_schema.properties must be an object")
    return _json_safe(schema)


def build_virtual_record_td(
    *,
    thing_id: str,
    title: str,
    description: str,
    record_schema: dict[str, Any],
) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "latest_record": _property("Most recent validated record.", {"type": "object"}),
        "record_count": _property("Number of stored records.", {"type": "integer"}),
        "last_recorded_at": _property(
            "Timestamp of the most recent stored record.",
            {"type": "string", "format": "date-time"},
        ),
    }
    for field_name, field_schema in _scalar_schema_fields(record_schema).items():
        properties[f"latest_{_safe_affordance_name(field_name)}"] = _property(
            f"Most recent value for {field_name}.",
            field_schema,
        )

    td = {
        "@context": "https://www.w3.org/2022/wot/td/v1.1",
        "id": thing_id,
        "title": title,
        "description": description,
        "tags": ["virtual", "records", "generated", "job"],
        "securityDefinitions": {"nosec_sc": {"scheme": "nosec"}},
        "security": "nosec_sc",
        "properties": properties,
        "actions": {
            "query_records": {
                "description": "Query stored records by time range.",
                "safe": True,
                "input": _query_input_schema(),
                "output": {"type": "array", "items": {"type": "object"}},
                "forms": [_form("query_records", "invokeaction")],
            },
            "query_property_history": {
                "description": "Query historical values for one top-level record property.",
                "safe": True,
                "input": {
                    **_query_input_schema(),
                    "required": ["property"],
                },
                "output": {"type": "array", "items": {"type": "object"}},
                "forms": [_form("query_property_history", "invokeaction")],
            },
        },
    }
    return validate_document(td)


class VirtualRecordStore:
    def __init__(self, session_factory: sessionmaker[Session] | None = None) -> None:
        self._session_factory = session_factory or get_session_factory()

    def create_or_update_thing(
        self,
        *,
        thing_id: str,
        source_job_id: str,
        schema_version: int,
        record_schema: dict[str, Any],
        title: str,
        description: str,
    ) -> dict[str, Any]:
        schema = validate_record_schema(record_schema)
        td = build_virtual_record_td(
            thing_id=thing_id,
            title=title,
            description=description,
            record_schema=schema,
        )
        now = utc_now()
        with self._session_factory() as session:
            row = session.get(VirtualRecordThing, thing_id)
            if row is None:
                row = VirtualRecordThing(
                    id=thing_id,
                    source_job_id=source_job_id,
                    schema_version=schema_version,
                    record_schema=schema,
                    title=title,
                    description=description,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.source_job_id = source_job_id
                row.schema_version = schema_version
                row.record_schema = schema
                row.title = title
                row.description = description
                row.updated_at = now

            record, _created = put_thing(session, thing_id, td)
            enqueue_thing_event(session, build_change_event("update", record))
            session.commit()
            return {"thing_id": thing_id, "td": td}

    def delete_thing(self, thing_id: str) -> None:
        with self._session_factory() as session:
            row = session.get(VirtualRecordThing, thing_id)
            if row is not None:
                session.delete(row)
            if delete_thing(session, thing_id):
                enqueue_thing_event(session, build_remove_event(thing_id))
            session.commit()

    def submit_record(
        self,
        *,
        thing_id: str,
        source_job_id: str,
        source_run_id: str,
        data: dict[str, Any],
        raw_input: str | None = None,
        confidence: float | None = None,
        recorded_at: datetime | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        with self._session_factory() as session:
            thing = session.get(VirtualRecordThing, thing_id)
            if thing is None:
                raise KeyError(thing_id)
            _validate_record_data(thing.record_schema, data)
            existing = session.scalars(
                select(VirtualRecord).where(
                    VirtualRecord.thing_id == thing_id,
                    VirtualRecord.source_run_id == source_run_id,
                )
            ).one_or_none()
            if existing is not None:
                return _record_payload(existing)

            record = VirtualRecord(
                id=str(uuid4()),
                thing_id=thing_id,
                schema_version=thing.schema_version,
                source_job_id=source_job_id,
                source_run_id=source_run_id,
                recorded_at=recorded_at or now,
                data=_json_safe(data),
                raw_input=raw_input,
                confidence=confidence,
                created_at=now,
                updated_at=now,
            )
            session.add(record)
            session.commit()
            return _record_payload(record)

    def read_property(self, thing_id: str, property_name: str) -> Any:
        with self._session_factory() as session:
            self._get_thing_or_404(session, thing_id)
            if property_name == "record_count":
                return int(
                    session.scalar(
                        select(func.count()).select_from(VirtualRecord).where(
                            VirtualRecord.thing_id == thing_id
                        )
                    )
                    or 0
                )

            latest = self._latest_record(session, thing_id)
            if property_name == "latest_record":
                return _record_payload(latest) if latest is not None else None
            if property_name == "last_recorded_at":
                return iso(latest.recorded_at) if latest is not None else None
            if property_name.startswith("latest_"):
                field = _field_name_for_property(
                    self._get_thing_or_404(session, thing_id).record_schema,
                    property_name.removeprefix("latest_"),
                )
                if field is None:
                    raise KeyError(property_name)
                return latest.data.get(field) if latest is not None else None
            raise KeyError(property_name)

    def invoke_action(self, thing_id: str, action_name: str, input_data: Any) -> Any:
        if action_name == "query_records":
            return self.query_records(thing_id, input_data if isinstance(input_data, dict) else {})
        if action_name == "query_property_history":
            if not isinstance(input_data, dict):
                raise ValueError("query_property_history requires an object input")
            field = input_data.get("property")
            if not isinstance(field, str) or not field.strip():
                raise ValueError("query_property_history requires property")
            return self.query_property_history(thing_id, field.strip(), input_data)
        raise KeyError(action_name)

    def query_records(self, thing_id: str, query: dict[str, Any]) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            self._get_thing_or_404(session, thing_id)
            statement = self._filtered_records_statement(thing_id, query)
            rows = session.scalars(statement).all()
            return [_record_payload(row) for row in rows]

    def query_property_history(
        self,
        thing_id: str,
        field_name: str,
        query: dict[str, Any],
    ) -> list[dict[str, Any]]:
        with self._session_factory() as session:
            thing = self._get_thing_or_404(session, thing_id)
            real_field = _field_name_for_property(thing.record_schema, field_name) or field_name
            statement = self._filtered_records_statement(thing_id, query)
            rows = session.scalars(statement).all()
            return [
                {
                    "recorded_at": iso(row.recorded_at),
                    "value": row.data.get(real_field),
                    "source_run_id": row.source_run_id,
                }
                for row in rows
                if isinstance(row.data, dict) and real_field in row.data
            ]

    def _get_thing_or_404(self, session: Session, thing_id: str) -> VirtualRecordThing:
        thing = session.get(VirtualRecordThing, thing_id)
        if thing is None:
            raise KeyError(thing_id)
        return thing

    def _latest_record(self, session: Session, thing_id: str) -> VirtualRecord | None:
        return session.scalars(
            select(VirtualRecord)
            .where(VirtualRecord.thing_id == thing_id)
            .order_by(VirtualRecord.recorded_at.desc(), VirtualRecord.created_at.desc())
            .limit(1)
        ).one_or_none()

    def _filtered_records_statement(self, thing_id: str, query: dict[str, Any]):
        statement = select(VirtualRecord).where(VirtualRecord.thing_id == thing_id)
        from_dt = _parse_datetime(query.get("from"))
        to_dt = _parse_datetime(query.get("to"))
        if from_dt is not None:
            statement = statement.where(VirtualRecord.recorded_at >= from_dt)
        if to_dt is not None:
            statement = statement.where(VirtualRecord.recorded_at <= to_dt)
        limit = _bounded_limit(query.get("limit"))
        return statement.order_by(VirtualRecord.recorded_at.asc()).limit(limit)


def _validate_record_data(schema: Any, data: Any) -> None:
    if not isinstance(data, dict):
        raise ValueError("structured record data must be an object")
    try:
        Draft202012Validator(schema).validate(data)
    except ValidationError as exc:
        path = ".".join(str(part) for part in exc.path)
        location = f" at {path}" if path else ""
        raise ValueError(f"record data failed schema validation{location}: {exc.message}") from exc


def _record_payload(row: VirtualRecord) -> dict[str, Any]:
    return {
        "id": row.id,
        "thing_id": row.thing_id,
        "schema_version": row.schema_version,
        "source_job_id": row.source_job_id,
        "source_run_id": row.source_run_id,
        "recorded_at": iso(row.recorded_at),
        "data": row.data,
        "raw_input": row.raw_input,
        "confidence": row.confidence,
    }


def _scalar_schema_fields(record_schema: dict[str, Any]) -> dict[str, dict[str, Any]]:
    properties = record_schema.get("properties")
    if not isinstance(properties, dict):
        return {}
    fields: dict[str, dict[str, Any]] = {}
    for name, schema in properties.items():
        if not isinstance(name, str) or not isinstance(schema, dict):
            continue
        schema_type = schema.get("type")
        if schema_type in {"string", "integer", "number", "boolean"} or "enum" in schema:
            fields[name] = schema
    return fields


def _property(description: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        **schema,
        "description": description,
        "readOnly": True,
        "forms": [_form("property", "readproperty")],
    }


def _query_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "from": {"type": "string", "format": "date-time"},
            "to": {"type": "string", "format": "date-time"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
        },
    }


def _form(path: str, op: str) -> dict[str, Any]:
    return {
        "href": f"urn:smart-living-copilot:virtual-records:{path}",
        "op": [op],
        "contentType": "application/json",
    }


def _safe_affordance_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "_", name).strip("_")
    return value or "value"


def _field_name_for_property(record_schema: Any, property_suffix: str) -> str | None:
    properties = record_schema.get("properties") if isinstance(record_schema, dict) else {}
    if not isinstance(properties, dict):
        return None
    for field_name in properties:
        if isinstance(field_name, str) and _safe_affordance_name(field_name) == property_suffix:
            return field_name
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _bounded_limit(value: Any) -> int:
    if isinstance(value, int):
        return min(max(value, 1), 1000)
    return 100


def virtual_record_http_error(error: Exception) -> HTTPException:
    if isinstance(error, KeyError):
        return HTTPException(status_code=404, detail=str(error))
    if isinstance(error, ValueError):
        return HTTPException(status_code=400, detail=str(error))
    return HTTPException(status_code=502, detail=str(error))
