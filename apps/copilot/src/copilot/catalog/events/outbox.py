import logging
from collections.abc import Collection
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from copilot.catalog.events.models import ThingEventOutbox, ThingEventOutboxRecord
from copilot.catalog.events.publisher import ThingEventPublisher

if TYPE_CHECKING:
    from copilot.catalog.events.worker import ThingEventOutboxPublisherState


logger = logging.getLogger(__name__)
DEFAULT_OUTBOX_BATCH_SIZE = 20


def _record_from_outbox(row: ThingEventOutbox) -> ThingEventOutboxRecord:
    return ThingEventOutboxRecord(
        id=row.id,
        event_type=row.event_type,
        thing_id=row.thing_id,
        event_hash=row.event_hash,
        payload_json=dict(row.payload_json or {}),
        created_at=row.created_at,
        published_at=row.published_at,
        attempt_count=row.attempt_count,
        last_error=row.last_error,
    )


def enqueue_thing_event(
    session: Session,
    event: dict[str, Any],
) -> ThingEventOutboxRecord:
    row = ThingEventOutbox(
        event_type=str(event.get("eventType", "")),
        thing_id=str(event.get("id", "")),
        event_hash=str(event.get("hash", "")),
        payload_json=event,
    )
    session.add(row)
    session.flush()
    return _record_from_outbox(row)


def list_pending_thing_events(
    session: Session,
    *,
    limit: int = DEFAULT_OUTBOX_BATCH_SIZE,
) -> list[ThingEventOutboxRecord]:
    rows = session.scalars(
        select(ThingEventOutbox)
        .where(ThingEventOutbox.published_at.is_(None))
        .order_by(ThingEventOutbox.id.asc())
        .limit(limit)
    ).all()
    return [_record_from_outbox(row) for row in rows]


def _claim_next_pending_event(
    session: Session,
    *,
    processed_ids: Collection[int],
) -> ThingEventOutbox | None:
    filters = [ThingEventOutbox.published_at.is_(None)]
    if processed_ids:
        filters.append(ThingEventOutbox.id.notin_(tuple(processed_ids)))

    return session.scalar(
        select(ThingEventOutbox)
        .where(*filters)
        .order_by(ThingEventOutbox.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )


def _publish_next_pending_event(
    session_factory: sessionmaker[Session],
    publisher: ThingEventPublisher,
    *,
    processed_ids: set[int],
    state: "ThingEventOutboxPublisherState | None",
) -> tuple[bool, bool]:
    with session_factory() as session:
        row = _claim_next_pending_event(session, processed_ids=processed_ids)
        if row is None:
            return False, False

        processed_ids.add(row.id)
        try:
            publisher.publish(dict(row.payload_json))
        except Exception as exc:
            row.attempt_count += 1
            row.last_error = str(exc)
            session.commit()
            logger.exception("Failed to publish queued Thing event id=%s", row.id)
            if state is not None:
                state.last_error = str(exc)
            return True, False

        row.attempt_count += 1
        row.last_error = ""
        row.published_at = datetime.now(timezone.utc)
        session.commit()

        if state is not None:
            state.last_error = ""
            state.last_published_id = row.id

        return True, True


def publish_pending_thing_events(
    session_factory: sessionmaker[Session],
    publisher: ThingEventPublisher,
    *,
    limit: int = DEFAULT_OUTBOX_BATCH_SIZE,
    state: "ThingEventOutboxPublisherState | None" = None,
) -> int:
    published_count = 0
    processed_ids: set[int] = set()

    for _ in range(max(0, limit)):
        found, published = _publish_next_pending_event(
            session_factory,
            publisher,
            processed_ids=processed_ids,
            state=state,
        )
        if not found:
            break
        if published:
            published_count += 1

    if state is not None:
        state.last_batch_size = published_count

    return published_count
