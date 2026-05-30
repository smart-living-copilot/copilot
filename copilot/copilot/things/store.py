import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from copilot.core.database import DatabaseConnection
from copilot.things.models import (
    ThingConflictError,
    ThingDocument,
    ThingRecord,
    ThingRow,
)

_THING_COLUMNS = """
    id, title, description, tags, document, document_hash, created_at, updated_at
"""


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


def _row_from_mapping(row: dict[str, Any]) -> ThingRow:
    return ThingRow(
        id=str(row["id"]),
        title=str(row["title"]),
        description=str(row["description"]),
        tags=list(row["tags"] or []),
        document=dict(row["document"] or {}),
        document_hash=str(row["document_hash"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


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
    connection: DatabaseConnection,
    *,
    query: str = "",
    page: int = 1,
    per_page: int = 25,
) -> tuple[list[ThingRecord], int]:
    normalized_query = query.strip().lower()
    offset = (page - 1) * per_page

    if normalized_query:
        pattern = f"%{normalized_query}%"
        where_sql = """
            WHERE lower(id) LIKE %s
               OR lower(title) LIKE %s
               OR lower(description) LIKE %s
               OR lower(document::text) LIKE %s
        """
        where_params: tuple[Any, ...] = (pattern, pattern, pattern, pattern)
    else:
        where_sql = ""
        where_params = ()

    total_row = connection.execute(
        f"SELECT COUNT(*) AS total FROM things {where_sql}",
        where_params,
    ).fetchone()
    total = int(total_row["total"]) if total_row else 0

    rows = connection.execute(
        f"""
        SELECT {_THING_COLUMNS}
        FROM things
        {where_sql}
        ORDER BY lower(title), id
        OFFSET %s
        LIMIT %s
        """,
        (*where_params, offset, per_page),
    ).fetchall()
    return [to_record(_row_from_mapping(row)) for row in rows], total


def get_thing(connection: DatabaseConnection, thing_id: str) -> ThingRecord | None:
    row = connection.execute(
        f"SELECT {_THING_COLUMNS} FROM things WHERE id = %s",
        (thing_id,),
    ).fetchone()
    return to_record(_row_from_mapping(row)) if row is not None else None


def create_thing(
    connection: DatabaseConnection,
    document: ThingDocument,
    *,
    commit: bool = True,
) -> ThingRecord:
    sanitized = sanitize_document(document)
    thing_id, title, tags, description = summarize_document(sanitized)

    try:
        row = connection.execute(
            f"""
            INSERT INTO things (
                id, title, description, tags, document, document_hash, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING {_THING_COLUMNS}
            """,
            (
                thing_id,
                title,
                description,
                Jsonb(tags),
                Jsonb(sanitized),
                hash_document(sanitized),
                datetime.now(timezone.utc),
            ),
        ).fetchone()
    except UniqueViolation as exc:
        connection.rollback()
        raise ThingConflictError(f"Thing '{thing_id}' already exists") from exc

    if commit:
        connection.commit()
    if row is None:
        raise RuntimeError(f"Thing {thing_id} could not be created")
    return to_record(_row_from_mapping(row))


def put_thing(
    connection: DatabaseConnection,
    thing_id: str,
    document: ThingDocument,
    *,
    commit: bool = True,
) -> tuple[ThingRecord, bool]:
    sanitized = sanitize_document(document)
    document_id, title, tags, description = summarize_document(sanitized)
    if document_id != thing_id:
        raise ValueError("Thing id in path and document body must match")

    document_hash = hash_document(sanitized)
    updated_at = datetime.now(timezone.utc)
    row = connection.execute(
        f"""
        INSERT INTO things (
            id, title, description, tags, document, document_hash, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO UPDATE
        SET title = EXCLUDED.title,
            description = EXCLUDED.description,
            tags = EXCLUDED.tags,
            document = EXCLUDED.document,
            document_hash = EXCLUDED.document_hash,
            updated_at = EXCLUDED.updated_at
        RETURNING {_THING_COLUMNS}, (xmax = 0) AS inserted
        """,
        (
            thing_id,
            title,
            description,
            Jsonb(tags),
            Jsonb(sanitized),
            document_hash,
            updated_at,
        ),
    ).fetchone()

    if commit:
        connection.commit()
    if row is None:
        raise RuntimeError(f"Thing {thing_id} could not be upserted")
    return to_record(_row_from_mapping(row)), bool(row["inserted"])


def delete_thing(
    connection: DatabaseConnection,
    thing_id: str,
    *,
    commit: bool = True,
) -> bool:
    row = connection.execute(
        "DELETE FROM things WHERE id = %s RETURNING id",
        (thing_id,),
    ).fetchone()
    if commit:
        connection.commit()
    return row is not None
