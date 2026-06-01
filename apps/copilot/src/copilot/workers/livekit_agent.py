"""LiveKit Agents worker that uses the existing LangGraph copilot brain."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from typing import Any

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:  # pragma: no cover - optional dependency guard.
    AsyncPostgresSaver = None  # type: ignore[assignment]

from langchain_core.messages import HumanMessage

from copilot.agent import build_graph
from copilot.agent.tools import LOCAL_TOOLS, REGISTRY_TOOLS
from copilot.agent.voice import voice_stream_text_from_event
from copilot.core.config import get_settings as get_registry_settings
from copilot.core.database import init_db, psycopg_conninfo
from copilot.core.llm import make_llm
from copilot.core.settings import Settings
from copilot.jobs.active import set_active_job_service
from copilot.jobs.service import JobService
from copilot.media import encode_frame_to_jpeg, media_sessions
from copilot.search import ThingSearchService, set_active_search_service
from copilot.threads import init_thread_store, touch_thread

logger = logging.getLogger(__name__)

_runtime_lock = asyncio.Lock()
_runtime_ref_count = 0
_job_service: JobService | None = None
_search_service: ThingSearchService | None = None


class CopilotVoiceAgent:
    """Small factory wrapper so LiveKit imports stay local to the worker role."""

    @staticmethod
    def create():
        from livekit.agents import Agent

        return Agent(
            instructions=(
                "You are Smart Living Copilot. Keep spoken replies concise and use the "
                "connected LangGraph workflow for reasoning, tools, and memory."
            )
        )


def _latest_user_turn_state(state: Any) -> Any:
    """Reduce adapter input to just the newest user message.

    The LiveKit ``LLMAdapter`` replays the entire ``chat_ctx`` as graph input on
    every turn, but the graph already persists history through its checkpointer.
    Feeding both duplicates every assistant message in state (the replayed
    copies carry LiveKit ids that don't match the checkpointed ones, so
    ``add_messages`` can't dedupe them), which eventually makes the model echo
    its own answers. Keep only the latest human turn and let the checkpointer
    own history.
    """
    if not isinstance(state, dict):
        return state
    messages = state.get("messages")
    if not isinstance(messages, list):
        return state
    last_human = next(
        (m for m in reversed(messages) if isinstance(m, HumanMessage)),
        None,
    )
    if last_human is None:
        return state
    return {**state, "messages": [last_human]}


class VoiceSafeGraphStream:
    """Filter LangGraph message streams to voice-safe assistant text chunks."""

    def __init__(self, graph: Any) -> None:
        self._graph = graph

    def __getattr__(self, name: str) -> Any:
        return getattr(self._graph, name)

    def astream(self, *args: Any, **kwargs: Any):
        if args:
            args = (_latest_user_turn_state(args[0]), *args[1:])
        events = self._graph.astream(*args, **kwargs)

        async def filtered_events():
            async for event in events:
                if voice_stream_text_from_event(event):
                    yield event

        return filtered_events()


def _livekit_media_session_id(ctx: Any, thread_id: str) -> str:
    room_name = getattr(getattr(ctx, "room", None), "name", "")
    if isinstance(room_name, str) and room_name:
        return f"livekit-{room_name}"
    return f"livekit-{thread_id}"


def _livekit_video_frame_to_bgr_array(frame: Any):
    from livekit.rtc.video_frame import proto_video
    import numpy as np

    rgb_frame = (
        frame
        if frame.type == proto_video.VideoBufferType.RGB24
        else frame.convert(proto_video.VideoBufferType.RGB24)
    )
    rgb_array = np.frombuffer(rgb_frame.data, dtype=np.uint8).reshape(
        (rgb_frame.height, rgb_frame.width, 3)
    )
    return rgb_array[:, :, ::-1].copy()


async def _capture_livekit_video_track(
    *,
    track: Any,
    session_id: str,
    thread_id: str,
) -> None:
    from livekit import rtc
    from livekit.rtc.video_frame import proto_video

    media_sessions.set_metadata(session_id, thread_id=thread_id)
    try:
        stream = rtc.VideoStream.from_track(
            track=track,
            format=proto_video.VideoBufferType.RGB24,
            capacity=1,
        )
    except Exception:
        logger.exception(
            "Failed to open LiveKit VideoStream for thread_id=%s", thread_id
        )
        return
    last_jpeg_encode_at = 0.0
    logged_first_snapshot = False
    try:
        async for event in stream:
            frame = event.frame
            media_sessions.record_video(
                session_id,
                width=int(frame.width),
                height=int(frame.height),
            )

            now = time.monotonic()
            if now - last_jpeg_encode_at < 0.33:
                continue
            last_jpeg_encode_at = now

            try:
                jpeg_bytes = encode_frame_to_jpeg(_livekit_video_frame_to_bgr_array(frame))
            except Exception:
                logger.debug("Failed to capture LiveKit video frame for vision", exc_info=True)
                continue
            if jpeg_bytes is not None:
                media_sessions.store_video_frame_jpeg(
                    session_id,
                    jpeg_bytes=jpeg_bytes,
                )
                if not logged_first_snapshot:
                    logger.info(
                        "LiveKit camera snapshot available for thread_id=%s",
                        thread_id,
                    )
                    logged_first_snapshot = True
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("LiveKit camera capture failed for thread_id=%s", thread_id)
    finally:
        await stream.aclose()


@asynccontextmanager
async def _livekit_camera_capture(ctx: Any, thread_id: str):
    from livekit import rtc

    room = getattr(ctx, "room", None)
    if room is None:
        yield
        return

    session_id = _livekit_media_session_id(ctx, thread_id)
    media_sessions.set_metadata(session_id, thread_id=thread_id)
    tasks_by_track_sid: dict[str, asyncio.Task[None]] = {}

    def track_sid(track: Any) -> str:
        sid = getattr(track, "sid", "")
        return sid if isinstance(sid, str) and sid else str(id(track))

    def is_video_track(track: Any) -> bool:
        return getattr(track, "kind", None) == rtc.TrackKind.KIND_VIDEO

    def is_video_publication(publication: Any) -> bool:
        return getattr(publication, "kind", None) == rtc.TrackKind.KIND_VIDEO

    def ensure_subscribed(publication: Any) -> None:
        """Explicitly subscribe to a remote video publication.

        RoomIO only subscribes to the audio it needs, so the camera track is
        never subscribed unless we ask for it. Requesting the subscription here
        is what drives the ``track_subscribed`` event that starts capture.
        """
        if not is_video_publication(publication):
            return
        set_subscribed = getattr(publication, "set_subscribed", None)
        if set_subscribed is None or getattr(publication, "subscribed", False):
            return
        try:
            set_subscribed(True)
            logger.debug(
                "Requested LiveKit video subscription for thread_id=%s sid=%s",
                thread_id,
                getattr(publication, "sid", "?"),
            )
        except Exception:
            logger.exception("Failed to subscribe to LiveKit video publication")

    def start_capture(track: Any) -> None:
        if not is_video_track(track):
            return
        sid = track_sid(track)
        if sid in tasks_by_track_sid:
            return
        task = asyncio.create_task(
            _capture_livekit_video_track(
                track=track,
                session_id=session_id,
                thread_id=thread_id,
            ),
            name=f"livekit-video-capture-{sid}",
        )
        tasks_by_track_sid[sid] = task
        logger.info("Started LiveKit camera capture for thread_id=%s track_sid=%s", thread_id, sid)

    async def stop_capture(track: Any) -> None:
        sid = track_sid(track)
        task = tasks_by_track_sid.pop(sid, None)
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def on_track_published(publication: Any, _participant: Any) -> None:
        ensure_subscribed(publication)

    def on_track_subscribed(track: Any, _publication: Any, _participant: Any) -> None:
        start_capture(track)

    def on_track_unsubscribed(track: Any, _publication: Any, _participant: Any) -> None:
        asyncio.create_task(stop_capture(track))

    room.on("track_published", on_track_published)
    room.on("track_subscribed", on_track_subscribed)
    room.on("track_unsubscribed", on_track_unsubscribed)

    for participant in getattr(room, "remote_participants", {}).values():
        for publication in getattr(participant, "track_publications", {}).values():
            ensure_subscribed(publication)
            track = getattr(publication, "track", None)
            if track is not None and getattr(publication, "subscribed", False):
                start_capture(track)

    try:
        yield
    finally:
        room.off("track_published", on_track_published)
        room.off("track_subscribed", on_track_subscribed)
        room.off("track_unsubscribed", on_track_unsubscribed)
        for task in tasks_by_track_sid.values():
            task.cancel()
        if tasks_by_track_sid:
            await asyncio.gather(*tasks_by_track_sid.values(), return_exceptions=True)
        media_sessions.close(session_id)


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
            await asyncio.to_thread(init_thread_store)

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
    try:
        candidates.append(getattr(ctx.token_claims(), "metadata", None))
    except Exception:
        pass

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


def _base_url_from_openai_endpoint(endpoint: str, *, suffix: str) -> str:
    normalized = endpoint.strip().rstrip("/")
    if not normalized:
        return ""
    if normalized.endswith(suffix):
        return normalized[: -len(suffix)].rstrip("/")
    return normalized


def _maybe_set(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    return value or None


def _speech_api_key(
    *,
    endpoint_url: str,
    speech_api_key: str,
    openai_api_key: str,
) -> str:
    if _maybe_set(endpoint_url):
        return speech_api_key.strip()
    return speech_api_key.strip() or openai_api_key.strip()


def _stt_kwargs(settings: Settings) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"model": settings.stt_model}
    language = _maybe_set(settings.stt_language)
    if language:
        kwargs["language"] = language
    else:
        kwargs["detect_language"] = True
    base_url = _base_url_from_openai_endpoint(
        settings.stt_transcriptions_url,
        suffix="/audio/transcriptions",
    ) or settings.openai_base_url
    api_key = _speech_api_key(
        endpoint_url=settings.stt_transcriptions_url,
        speech_api_key=settings.stt_api_key,
        openai_api_key=settings.openai_api_key,
    )
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key
    return kwargs


def _make_stt(settings: Settings):
    from livekit.plugins import openai

    kwargs = _stt_kwargs(settings)
    return openai.STT(**kwargs)


def _tts_kwargs(settings: Settings) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": settings.tts_model,
        "voice": settings.tts_voice,
        "speed": settings.tts_speed,
    }
    base_url = _base_url_from_openai_endpoint(
        settings.tts_speech_url,
        suffix="/audio/speech",
    ) or settings.openai_base_url
    api_key = _speech_api_key(
        endpoint_url=settings.tts_speech_url,
        speech_api_key=settings.tts_api_key,
        openai_api_key=settings.openai_api_key,
    )
    response_format = _maybe_set(settings.tts_response_format)
    if base_url:
        kwargs["base_url"] = base_url
    if api_key:
        kwargs["api_key"] = api_key
    if response_format:
        kwargs["response_format"] = response_format
    return kwargs


def _make_tts(settings: Settings):
    from livekit.plugins import openai

    kwargs = _tts_kwargs(settings)
    return openai.TTS(**kwargs)


def _compile_graph(settings: Settings, checkpointer: Any):
    llm = make_llm(settings)
    graph = build_graph(
        llm=llm,
        registry_tools=REGISTRY_TOOLS,
        local_tools=LOCAL_TOOLS,
        max_tokens=settings.max_context_tokens,
        checkpointer=checkpointer,
        parallel_tool_calls=settings.parallel_tool_calls,
        vision_enabled=settings.vision_enabled,
    )
    return graph.with_config(recursion_limit=settings.recursion_limit)


async def _wait_for_shutdown(ctx: Any) -> None:
    shutdown_event = asyncio.Event()

    async def on_shutdown(_reason: str = "") -> None:
        shutdown_event.set()

    ctx.add_shutdown_callback(on_shutdown)
    await shutdown_event.wait()


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
        _livekit_camera_capture(ctx, thread_id),
    ):
        graph = _compile_graph(settings, saver)
        session = AgentSession(
            stt=_make_stt(settings),
            llm=langchain.LLMAdapter(
                graph=VoiceSafeGraphStream(graph),
                config={"configurable": {"thread_id": thread_id}},
            ),
            tts=_make_tts(settings),
            vad=silero.VAD.load(),
            # Preemptive generation speculatively runs the LLM on the interim
            # transcript and cannot reuse a LangGraph adapter's output, so the
            # graph runs (and the answer is spoken) twice per turn. Disable it.
            preemptive_generation=False,
        )
        await session.start(
            room=ctx.room,
            agent=CopilotVoiceAgent.create(),
            room_options=room_io.RoomOptions(
                # Camera frames for look_at_camera are captured directly by
                # _livekit_camera_capture, so RoomIO's own video input stays off.
                text_output=room_io.TextOutputOptions(sync_transcription=False),
            ),
        )
        try:
            await _wait_for_shutdown(ctx)
        finally:
            session.shutdown(drain=True)
            await asyncio.to_thread(touch_thread, thread_id)


async def smart_living_copilot(ctx: Any) -> None:
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
    server.rtc_session(agent_name=settings.livekit_agent_name)(smart_living_copilot)
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
