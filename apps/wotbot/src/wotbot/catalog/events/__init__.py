"""Catalog event and outbox domain.

The events package turns catalog mutations into durable payloads, stores them for
delivery in an outbox, and publishes them through pluggable publishers to
streams used by indexers and background workers.
"""

from wotbot.catalog.events.outbox import (
    enqueue_thing_event,
    list_pending_thing_events,
    publish_pending_thing_events,
)
from wotbot.catalog.events.payloads import build_change_event, build_remove_event
from wotbot.catalog.events.publisher import (
    NoopThingEventPublisher,
    ThingEventPublisher,
    ValkeyThingEventStreamPublisher,
)
from wotbot.catalog.events.worker import (
    ThingEventOutboxPublisherState,
    ThingEventOutboxPublisherWorker,
)

__all__ = [
    "NoopThingEventPublisher",
    "ThingEventOutboxPublisherState",
    "ThingEventOutboxPublisherWorker",
    "ThingEventPublisher",
    "ValkeyThingEventStreamPublisher",
    "build_change_event",
    "build_remove_event",
    "enqueue_thing_event",
    "list_pending_thing_events",
    "publish_pending_thing_events",
]
