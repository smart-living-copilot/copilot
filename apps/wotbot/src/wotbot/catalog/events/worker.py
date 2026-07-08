import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from wotbot.catalog.events.outbox import (
    DEFAULT_OUTBOX_BATCH_SIZE,
    publish_pending_thing_events,
)
from wotbot.catalog.events.publisher import ThingEventPublisher

logger = logging.getLogger(__name__)
DEFAULT_OUTBOX_POLL_INTERVAL_SECONDS = 0.5


@dataclass
class ThingEventOutboxPublisherState:
    task: asyncio.Task[None] | None = None
    loop_running: bool = False
    last_error: str = ""
    last_published_id: int | None = None
    last_batch_size: int = 0


class ThingEventOutboxPublisherWorker:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        publisher_getter: Callable[[], ThingEventPublisher],
        state: ThingEventOutboxPublisherState,
        batch_size: int = DEFAULT_OUTBOX_BATCH_SIZE,
        poll_interval_seconds: float = DEFAULT_OUTBOX_POLL_INTERVAL_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._publisher_getter = publisher_getter
        self._state = state
        self._batch_size = batch_size
        self._poll_interval_seconds = poll_interval_seconds

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        self._state.loop_running = True
        self._state.last_error = ""
        try:
            while not stop_event.is_set():
                try:
                    published_count = publish_pending_thing_events(
                        self._session_factory,
                        self._publisher_getter(),
                        limit=self._batch_size,
                        state=self._state,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self._state.last_error = str(exc)
                    logger.exception("Thing event outbox publisher loop failed")
                    published_count = 0

                if published_count > 0:
                    continue

                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=self._poll_interval_seconds,
                    )
                except TimeoutError:
                    continue
        finally:
            self._state.loop_running = False
