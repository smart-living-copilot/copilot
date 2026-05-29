import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.orm import Session

from copilot.things.models import (
    ThingConflictError,
    ThingDocument,
    ThingRecord,
    ThingRow,
)


def sanitize_document(document: ThingDocument) -> ThingDocument:
    return {key: value for key, value in document.items() if key != "hash"}


def _normalize_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    tags: list[str] = []
    for item in value:
        if isinstance(item, (str, int, float, bool)):
            tags.append(str(item))
    return tags


def summarize_document(document: ThingDocument) -> tuple[str, str, list[str], str]:
    thing_id = document.get("id")
    if not isinstance(thing_id, str) or not thing_id.strip():
        raise ValueError("Thing Description is missing a valid 'id'")

    title = document.get("title")
    if not isinstance(title, str) or not title.strip():
        title = thing_id

    description = document.get("description")
    if not isinstance(description, str):
        description = ""

    return thing_id, title, _normalize_tags(document.get("tags")), description


def hash_document(document: ThingDocument) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def to_record(row: ThingRow) -> ThingRecord:
    return ThingRecord(
        id=row.id,
        title=row.title,
        description=row.description,
        tags=list(row.tags or []),
        document=dict(row.document),
        document_hash=row.document_hash,
    )


def serialize_document(record: ThingRecord) -> ThingDocument:
    return dict(record.document)


def list_things(
    session: Session,
    *,
    query: str = "",
    page: int = 1,
    per_page: int = 25,
) -> tuple[list[ThingRecord], int]:
    statement = select(ThingRow)
    normalized_query = query.strip().lower()

    if normalized_query:
        pattern = f"%{normalized_query}%"
        statement = statement.where(
            or_(
                func.lower(ThingRow.id).like(pattern),
                func.lower(ThingRow.title).like(pattern),
                func.lower(ThingRow.description).like(pattern),
                func.lower(cast(ThingRow.document, Text)).like(pattern),
            )
        )

    count_statement = select(func.count()).select_from(statement.subquery())
    total = session.execute(count_statement).scalar_one()

    statement = statement.order_by(func.lower(ThingRow.title), ThingRow.id)
    statement = statement.offset((page - 1) * per_page).limit(per_page)
    rows = session.execute(statement).scalars().all()
    return [to_record(row) for row in rows], total


def get_thing(session: Session, thing_id: str) -> ThingRecord | None:
    row = session.get(ThingRow, thing_id)
    if row is None:
        return None
    return to_record(row)


def create_thing(
    session: Session,
    document: ThingDocument,
    *,
    commit: bool = True,
) -> ThingRecord:
    sanitized = sanitize_document(document)
    thing_id, title, tags, description = summarize_document(sanitized)

    if session.get(ThingRow, thing_id) is not None:
        raise ThingConflictError(f"Thing '{thing_id}' already exists")

    row = ThingRow(
        id=thing_id,
        title=title,
        description=description,
        tags=tags,
        document=sanitized,
        document_hash=hash_document(sanitized),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(row)
    session.flush()
    if commit:
        session.commit()
        session.refresh(row)
    return to_record(row)


def put_thing(
    session: Session,
    thing_id: str,
    document: ThingDocument,
    *,
    commit: bool = True,
) -> tuple[ThingRecord, bool]:
    sanitized = sanitize_document(document)
    document_id, title, tags, description = summarize_document(sanitized)
    if document_id != thing_id:
        raise ValueError("Thing id in path and document body must match")

    row = session.get(ThingRow, thing_id)
    created = row is None

    if row is None:
        row = ThingRow(
            id=thing_id,
            title=title,
            description=description,
            tags=tags,
            document=sanitized,
            document_hash=hash_document(sanitized),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(row)
    else:
        row.title = title
        row.description = description
        row.tags = tags
        row.document = sanitized
        row.document_hash = hash_document(sanitized)
        row.updated_at = datetime.now(timezone.utc)

    session.flush()
    if commit:
        session.commit()
        session.refresh(row)
    return to_record(row), created


def delete_thing(session: Session, thing_id: str, *, commit: bool = True) -> bool:
    row = session.get(ThingRow, thing_id)
    if row is None:
        return False

    session.delete(row)
    if commit:
        session.commit()
    return True
