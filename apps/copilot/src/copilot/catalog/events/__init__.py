"""Catalog event and outbox domain.

The events package turns catalog mutations into durable payloads, stores them for
delivery in an outbox, and publishes them through pluggable publishers to
streams used by indexers and background workers.
"""

from copilot.catalog.events.payloads import build_change_event, build_remove_event
from copilot.catalog.events.outbox import (
    enqueue_thing_event,
    list_pending_thing_events,
    publish_pending_thing_events,
)
from copilot.catalog.events.publisher import (
    NoopThingEventPublisher,
    ThingEventPublisher,
    ValkeyThingEventStreamPublisher,
)
from copilot.catalog.events.worker import (
    ThingEventOutboxPublisherState,
    ThingEventOutboxPublisherWorker,
)

__all__ = [
    "build_change_event",
    "build_remove_event",
    "NoopThingEventPublisher",
    "ThingEventOutboxPublisherState",
    "ThingEventOutboxPublisherWorker",
    "ThingEventPublisher",
    "ValkeyThingEventStreamPublisher",
    "enqueue_thing_event",
    "list_pending_thing_events",
    "publish_pending_thing_events",
]
