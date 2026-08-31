from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol

from fastapi import FastAPI
from psycopg_pool import ConnectionPool

from wotbot.catalog.events import (
    ThingEventOutboxPublisherState,
    ThingEventOutboxPublisherWorker,
    ValkeyThingEventStreamPublisher,
)
from wotbot.core.bootstrap import BackendBootstrapService
from wotbot.core.config import Settings
from wotbot.core.database import DatabaseConnection, get_session_factory
from wotbot.discovery.store import reset_clients as reset_discovery_clients
from wotbot.search import ThingSearchService, set_active_search_service


class BackgroundTaskState(Protocol):
    task: asyncio.Task[None] | None


def initialize_app_state(
    app: FastAPI,
    *,
    settings: Settings,
    connection_pool: ConnectionPool[DatabaseConnection],
) -> None:
    session_factory = get_session_factory()
    app.state.connection_pool = connection_pool
    app.state.orm_session_factory = session_factory
    app.state.session_factory = session_factory
    app.state.event_publisher = ValkeyThingEventStreamPublisher(
        settings.REDIS_URL,
        settings.THING_EVENTS_STREAM,
    )
    app.state.thing_event_outbox_state = ThingEventOutboxPublisherState()
    app.state.thing_event_outbox_stop_event = asyncio.Event()
    app.state.thing_event_outbox_publisher = None

    app.state.search_service = None


def bootstrap_persistent_state(
    *,
    settings: Settings,
) -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        BackendBootstrapService(session).bootstrap(settings)


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
    settings: Settings,
) -> None:
    publisher = ThingEventOutboxPublisherWorker(
        session_factory=app.state.orm_session_factory,
        publisher_getter=lambda: app.state.event_publisher,
        state=app.state.thing_event_outbox_state,
        batch_size=settings.THING_EVENT_OUTBOX_BATCH_SIZE,
        poll_interval_seconds=settings.THING_EVENT_OUTBOX_POLL_INTERVAL_SECONDS,
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
    settings.validate_runtime_security_settings()
    initialize_app_state(app, settings=settings, connection_pool=connection_pool)
    bootstrap_persistent_state(settings=settings)

    try:
        start_thing_event_outbox(app, settings=settings)
        start_search_service(app, settings=settings)
    except Exception:
        await shutdown_backend_runtime(app)
        raise


async def shutdown_backend_runtime(app: FastAPI) -> None:
    await stop_search_service(app)
    await stop_thing_event_outbox(app)
    await reset_discovery_clients()
    app.state.event_publisher.close()
