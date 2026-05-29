import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from copilot.thing_events.models import ThingEventOutboxRow
from copilot.thing_events.publisher import ThingEventPublisher

if TYPE_CHECKING:
    from copilot.thing_events.worker import ThingEventOutboxPublisherState


logger = logging.getLogger(__name__)
OUTBOX_BATCH_SIZE = 20


def enqueue_thing_event(session: Session, event: dict[str, Any]) -> ThingEventOutboxRow:
    row = ThingEventOutboxRow(
        event_type=str(event.get("eventType", "")),
        thing_id=str(event.get("id", "")),
        event_hash=str(event.get("hash", "")),
        payload_json=event,
    )
    session.add(row)
    session.flush()
    return row


def list_pending_thing_events(
    session: Session,
    *,
    limit: int = OUTBOX_BATCH_SIZE,
) -> list[ThingEventOutboxRow]:
    statement = (
        select(ThingEventOutboxRow)
        .where(ThingEventOutboxRow.published_at.is_(None))
        .order_by(ThingEventOutboxRow.id.asc())
        .limit(limit)
    )
    return list(session.execute(statement).scalars().all())


def publish_pending_thing_events(
    session_factory: sessionmaker,
    publisher: ThingEventPublisher,
    *,
    limit: int = OUTBOX_BATCH_SIZE,
    state: "ThingEventOutboxPublisherState | None" = None,
) -> int:
    session = session_factory()
    try:
        rows = list_pending_thing_events(session, limit=limit)
        published_count = 0

        for row in rows:
            try:
                publisher.publish(dict(row.payload_json))
            except Exception as exc:
                row.attempt_count += 1
                row.last_error = str(exc)
                session.commit()
                logger.exception("Failed to publish queued Thing event id=%s", row.id)
                if state is not None:
                    state.last_error = str(exc)
                continue

            row.attempt_count += 1
            row.last_error = ""
            row.published_at = datetime.now(timezone.utc)
            session.commit()
            published_count += 1

            if state is not None:
                state.last_error = ""
                state.last_published_id = row.id

        if state is not None:
            state.last_batch_size = published_count

        return published_count
    finally:
        session.close()
