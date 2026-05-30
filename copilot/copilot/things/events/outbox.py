import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from copilot.core.database import DatabaseConnection
from copilot.things.events.models import ThingEventOutboxRow
from copilot.things.events.publisher import ThingEventPublisher

if TYPE_CHECKING:
    from copilot.things.events.worker import ThingEventOutboxPublisherState


logger = logging.getLogger(__name__)
OUTBOX_BATCH_SIZE = 20
_OUTBOX_COLUMNS = """
    id, event_type, thing_id, event_hash, payload_json, created_at,
    published_at, attempt_count, last_error
"""


def _row_from_mapping(row: dict[str, Any]) -> ThingEventOutboxRow:
    return ThingEventOutboxRow(
        id=int(row["id"]),
        event_type=str(row["event_type"]),
        thing_id=str(row["thing_id"]),
        event_hash=str(row["event_hash"]),
        payload_json=dict(row["payload_json"] or {}),
        created_at=row["created_at"],
        published_at=row["published_at"],
        attempt_count=int(row["attempt_count"] or 0),
        last_error=str(row["last_error"] or ""),
    )


def enqueue_thing_event(
    connection: DatabaseConnection,
    event: dict[str, Any],
) -> ThingEventOutboxRow:
    row = connection.execute(
        f"""
        INSERT INTO thing_event_outbox (
            event_type, thing_id, event_hash, payload_json
        )
        VALUES (%s, %s, %s, %s)
        RETURNING {_OUTBOX_COLUMNS}
        """,
        (
            str(event.get("eventType", "")),
            str(event.get("id", "")),
            str(event.get("hash", "")),
            Jsonb(event),
        ),
    ).fetchone()
    if row is None:
        raise RuntimeError("Thing event outbox row was not returned")
    return _row_from_mapping(row)


def list_pending_thing_events(
    connection: DatabaseConnection,
    *,
    limit: int = OUTBOX_BATCH_SIZE,
) -> list[ThingEventOutboxRow]:
    rows = connection.execute(
        f"""
        SELECT {_OUTBOX_COLUMNS}
        FROM thing_event_outbox
        WHERE published_at IS NULL
        ORDER BY id ASC
        LIMIT %s
        """,
        (limit,),
    ).fetchall()
    return [_row_from_mapping(row) for row in rows]


def publish_pending_thing_events(
    connection_pool: ConnectionPool[DatabaseConnection],
    publisher: ThingEventPublisher,
    *,
    limit: int = OUTBOX_BATCH_SIZE,
    state: "ThingEventOutboxPublisherState | None" = None,
) -> int:
    with connection_pool.connection() as connection:
        rows = list_pending_thing_events(connection, limit=limit)
        published_count = 0

        for row in rows:
            try:
                publisher.publish(dict(row.payload_json))
            except Exception as exc:
                connection.execute(
                    """
                    UPDATE thing_event_outbox
                    SET attempt_count = attempt_count + 1, last_error = %s
                    WHERE id = %s
                    """,
                    (str(exc), row.id),
                )
                connection.commit()
                logger.exception("Failed to publish queued Thing event id=%s", row.id)
                if state is not None:
                    state.last_error = str(exc)
                continue

            connection.execute(
                """
                UPDATE thing_event_outbox
                SET attempt_count = attempt_count + 1,
                    last_error = '',
                    published_at = %s
                WHERE id = %s
                """,
                (datetime.now(timezone.utc), row.id),
            )
            connection.commit()
            published_count += 1

            if state is not None:
                state.last_error = ""
                state.last_published_id = row.id

        if state is not None:
            state.last_batch_size = published_count

        return published_count
