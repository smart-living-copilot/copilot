"""LiveKit Agents worker that drives the LangGraph wotbot brain over voice."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import asynccontextmanager, suppress
from typing import Any

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:  # pragma: no cover - optional dependency guard.
    AsyncPostgresSaver = None  # type: ignore[assignment]

from wotbot.core.config import get_settings as get_registry_settings
from wotbot.core.database import init_db, psycopg_conninfo
from wotbot.core.settings import Settings
from wotbot.jobs.active import set_active_job_service
from wotbot.jobs.service import JobService
from wotbot.media import SNAPSHOT_EVENT_TYPE, SNAPSHOT_TOPIC, snapshot_notifiers
from wotbot.search import ThingSearchService, set_active_search_service
from wotbot.threads import touch_thread
from wotbot.workers.livekit.capture import livekit_camera_capture
from wotbot.workers.livekit.graph import VoiceSafeGraphStream, compile_graph
from wotbot.workers.livekit.speech import make_stt, make_tts

logger = logging.getLogger(__name__)

_runtime_lock = asyncio.Lock()
_runtime_ref_count = 0
_job_service: JobService | None = None
_search_service: ThingSearchService | None = None


class WotbotVoiceAgent:
    """Small factory wrapper so LiveKit imports stay local to the worker role."""

    @staticmethod
    def create():
        from livekit.agents import Agent

        return Agent(
            instructions=(
                "You are WoTBot. Keep spoken replies concise and use the "
                "connected LangGraph workflow for reasoning, tools, and memory."
            )
        )


def _checkpoint_database_url(*, settings: Settings, registry_database_url: str) -> str:
    return settings.agent_state_database_url or registry_database_url


@asynccontextmanager
async def _checkpoint_saver_context(
    *,
    settings: Settings,
    registry_database_url: str,
):
    if AsyncPostgresSaver is None:
        raise RuntimeError(
            "LiveKit voice agent checkpointing requires langgraph-checkpoint-postgres"
        )

    database_url = _checkpoint_database_url(
        settings=settings,
        registry_database_url=registry_database_url,
    )
    async with AsyncPostgresSaver.from_conn_string(psycopg_conninfo(database_url)) as saver:
        await saver.setup()
        yield saver


async def _start_shared_runtime(settings: Settings) -> None:
    global _job_service, _runtime_ref_count, _search_service

    async with _runtime_lock:
        if _runtime_ref_count == 0:
            registry_settings = get_registry_settings()
            await asyncio.to_thread(init_db)

            _search_service = ThingSearchService(registry_settings)
            set_active_search_service(_search_service)

            _job_service = JobService(settings)
            await _job_service.start()
            set_active_job_service(_job_service)

            logger.info("LiveKit agent shared runtime started")
        _runtime_ref_count += 1


async def _stop_shared_runtime() -> None:
    global _job_service, _runtime_ref_count, _search_service

    async with _runtime_lock:
        if _runtime_ref_count <= 0:
            return

        _runtime_ref_count -= 1
        if _runtime_ref_count > 0:
            return

        set_active_job_service(None)
        if _job_service is not None:
            await _job_service.stop()
            _job_service = None

        set_active_search_service(None)
        if _search_service is not None:
            await _search_service.close()
            _search_service = None

        logger.info("LiveKit agent shared runtime stopped")


@asynccontextmanager
async def _shared_runtime(settings: Settings):
    await _start_shared_runtime(settings)
    try:
        yield
    finally:
        await _stop_shared_runtime()


def _json_object(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _thread_id_from_context(ctx: Any, settings: Settings) -> str:
    candidates: list[str | None] = []
    job = getattr(ctx, "job", None)
    candidates.append(getattr(job, "metadata", None))
    with suppress(Exception):
        candidates.append(getattr(ctx.token_claims(), "metadata", None))

    for raw_metadata in candidates:
        metadata = _json_object(raw_metadata)
        for key in ("threadId", "thread_id"):
            value = metadata.get(key)
            if isinstance(value, str) and value:
                return value

    room_name = getattr(getattr(job, "room", None), "name", "") or getattr(
        getattr(ctx, "room", None),
        "name",
        "",
    )
    prefix = f"{settings.livekit_room_prefix}-"
    if isinstance(room_name, str) and room_name.startswith(prefix):
        return room_name[len(prefix) :]
    if isinstance(room_name, str) and room_name:
        return room_name
    return "default"


async def _wait_for_shutdown(ctx: Any) -> None:
    shutdown_event = asyncio.Event()

    async def on_shutdown(_reason: str = "") -> None:
        shutdown_event.set()

    ctx.add_shutdown_callback(on_shutdown)
    await shutdown_event.wait()


async def _publish_camera_snapshot(room: Any, captured_at: str | None) -> None:
    local_participant = getattr(room, "local_participant", None)
    publish_data = getattr(local_participant, "publish_data", None)
    if publish_data is None:
        logger.debug("LiveKit room has no local participant data publisher")
        return

    payload = json.dumps(
        {
            "type": SNAPSHOT_EVENT_TYPE,
            "capturedAt": captured_at,
        }
    )
    await publish_data(payload, reliable=True, topic=SNAPSHOT_TOPIC)


@asynccontextmanager
async def livekit_snapshot_notifications(room: Any, thread_id: str):
    unregister = snapshot_notifiers.register(
        thread_id,
        lambda captured_at: _publish_camera_snapshot(room, captured_at),
    )
    try:
        yield
    finally:
        unregister()


async def _run_livekit_session(ctx: Any, settings: Settings) -> None:
    from livekit.agents import AgentSession, room_io
    from livekit.plugins import langchain, silero

    thread_id = _thread_id_from_context(ctx, settings)
    registry_settings = get_registry_settings()
    logger.info("Starting LiveKit voice session for thread_id=%s", thread_id)

    async with (
        _shared_runtime(settings),
        _checkpoint_saver_context(
            settings=settings,
            registry_database_url=registry_settings.DATABASE_URL,
        ) as saver,
        livekit_camera_capture(ctx, thread_id),
        livekit_snapshot_notifications(ctx.room, thread_id),
    ):
        graph = compile_graph(settings, saver)
        session = AgentSession(
            stt=make_stt(settings),
            llm=langchain.LLMAdapter(
                graph=VoiceSafeGraphStream(graph),
                config={"configurable": {"thread_id": thread_id}},
            ),
            tts=make_tts(settings),
            vad=silero.VAD.load(),
            # Preemptive generation speculatively runs the LLM on the interim
            # transcript and cannot reuse a LangGraph adapter's output, so the
            # graph runs (and the answer is spoken) twice per turn. Disable it.
            preemptive_generation=False,
        )
        await session.start(
            room=ctx.room,
            agent=WotbotVoiceAgent.create(),
            room_options=room_io.RoomOptions(
                # Camera frames for look_at_camera are captured directly by
                # livekit_camera_capture, so RoomIO's own video input stays off.
                text_output=room_io.TextOutputOptions(sync_transcription=False),
            ),
        )
        try:
            await _wait_for_shutdown(ctx)
        finally:
            session.shutdown(drain=True)
            await asyncio.to_thread(touch_thread, thread_id)


async def wotbot(ctx: Any) -> None:
    """Top-level LiveKit session handler.

    LiveKit's dev watcher uses multiprocessing spawn, so registered session
    callbacks must be importable module-level functions.
    """
    await _run_livekit_session(ctx, Settings())


def create_server(settings: Settings | None = None):
    from livekit.agents import AgentServer

    settings = settings or Settings()
    server = AgentServer(
        ws_url=settings.livekit_url or None,
        api_key=settings.livekit_api_key or None,
        api_secret=settings.livekit_api_secret or None,
        log_level=settings.log_level,
    )
    server.rtc_session(agent_name=settings.livekit_agent_name)(wotbot)
    return server


def run(cli_args: list[str] | None = None) -> None:
    from livekit import agents

    settings = Settings()
    logging.basicConfig(level=settings.log_level)
    original_argv = sys.argv[:]
    sys.argv = [original_argv[0], *(cli_args or ["start"])]
    try:
        agents.cli.run_app(create_server(settings))
    finally:
        sys.argv = original_argv
