from __future__ import annotations

import asyncio
from typing import Awaitable, Callable, Protocol

from fastapi import FastAPI
from psycopg_pool import ConnectionPool

from copilot.core.config import Settings
from copilot.core.bootstrap import BackendBootstrapService
from copilot.core.database import DatabaseConnection
from copilot.search import ThingSearchService, set_active_search_service
from copilot.search.indexer.store import SearchVectorStore
from copilot.core.stream_runtime import StreamConsumerState
from copilot.things.events import (
    ThingEventOutboxPublisherState,
    ThingEventOutboxPublisherWorker,
    ValkeyThingEventStreamPublisher,
)


class BackgroundTaskState(Protocol):
    task: asyncio.Task[None] | None


def initialize_app_state(
    app: FastAPI,
    *,
    settings: Settings,
    connection_pool: ConnectionPool[DatabaseConnection],
) -> None:
    app.state.connection_pool = connection_pool
    app.state.event_publisher = ValkeyThingEventStreamPublisher(
        settings.REDIS_URL,
        settings.THING_EVENTS_STREAM,
    )
    app.state.thing_event_outbox_state = ThingEventOutboxPublisherState()
    app.state.thing_event_outbox_stop_event = asyncio.Event()
    app.state.thing_event_outbox_publisher = None

    app.state.search_indexer_consumer_state = StreamConsumerState()
    app.state.search_indexer_stop_event = asyncio.Event()
    app.state.search_indexer_consumer = None
    app.state.search_service = None


def bootstrap_persistent_state(
    *,
    connection_pool: ConnectionPool[DatabaseConnection],
    settings: Settings,
) -> None:
    with connection_pool.connection() as connection:
        BackendBootstrapService(connection).bootstrap(settings)


def _start_background_task(
    *,
    state: BackgroundTaskState,
    stop_event: asyncio.Event,
    runner: Callable[[asyncio.Event], Awaitable[None]],
) -> None:
    state.task = asyncio.create_task(runner(stop_event))


async def _stop_background_task(
    *,
    state: BackgroundTaskState,
    stop_event: asyncio.Event,
) -> None:
    stop_event.set()
    task = state.task
    if task is None:
        return

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        state.task = None


def start_thing_event_outbox(
    app: FastAPI,
    *,
    connection_pool: ConnectionPool[DatabaseConnection],
) -> None:
    publisher = ThingEventOutboxPublisherWorker(
        connection_pool=connection_pool,
        publisher_getter=lambda: app.state.event_publisher,
        state=app.state.thing_event_outbox_state,
    )
    app.state.thing_event_outbox_publisher = publisher
    _start_background_task(
        state=app.state.thing_event_outbox_state,
        stop_event=app.state.thing_event_outbox_stop_event,
        runner=publisher.run_forever,
    )


async def stop_thing_event_outbox(app: FastAPI) -> None:
    await _stop_background_task(
        state=app.state.thing_event_outbox_state,
        stop_event=app.state.thing_event_outbox_stop_event,
    )


async def start_search_indexer(
    app: FastAPI,
    *,
    settings: Settings,
    vector_store: SearchVectorStore | None = None,
) -> None:
    from copilot.search.indexer.consumer import SearchIndexerStreamConsumer

    consumer = SearchIndexerStreamConsumer(
        settings=settings,
        state=app.state.search_indexer_consumer_state,
        vector_store=vector_store,
    )
    app.state.search_indexer_consumer = consumer
    await consumer.start()
    _start_background_task(
        state=app.state.search_indexer_consumer_state,
        stop_event=app.state.search_indexer_stop_event,
        runner=consumer.run_forever,
    )


async def stop_search_indexer(app: FastAPI) -> None:
    await _stop_background_task(
        state=app.state.search_indexer_consumer_state,
        stop_event=app.state.search_indexer_stop_event,
    )

    consumer = app.state.search_indexer_consumer
    if consumer is not None:
        await consumer.close()
        app.state.search_indexer_consumer = None


def start_search_service(app: FastAPI, *, settings: Settings) -> None:
    service = ThingSearchService(settings)
    app.state.search_service = service
    set_active_search_service(service)


async def stop_search_service(app: FastAPI) -> None:
    search_service = app.state.search_service
    if search_service is not None:
        set_active_search_service(None)
        await search_service.close()
        app.state.search_service = None
        return

    set_active_search_service(None)


async def start_backend_runtime(
    app: FastAPI,
    *,
    settings: Settings,
    connection_pool: ConnectionPool[DatabaseConnection],
) -> None:
    settings.validate_search_settings()
    settings.validate_runtime_security_settings()
    initialize_app_state(app, settings=settings, connection_pool=connection_pool)
    bootstrap_persistent_state(connection_pool=connection_pool, settings=settings)

    try:
        start_thing_event_outbox(app, connection_pool=connection_pool)
        start_search_service(app, settings=settings)
        await start_search_indexer(
            app,
            settings=settings,
            vector_store=app.state.search_service.vector_store,
        )
    except Exception:
        await shutdown_backend_runtime(app)
        raise


async def shutdown_backend_runtime(app: FastAPI) -> None:
    await stop_search_service(app)
    await stop_thing_event_outbox(app)
    await stop_search_indexer(app)
    app.state.event_publisher.close()
