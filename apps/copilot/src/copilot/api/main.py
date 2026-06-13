"""FastAPI + AG-UI entrypoint for the Smart Living Copilot."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from ag_ui_langgraph import add_langgraph_fastapi_endpoint  # type: ignore[import-untyped]
from copilotkit import LangGraphAGUIAgent
from fastapi import FastAPI

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:  # pragma: no cover - exercised when optional dep is absent locally.
    AsyncPostgresSaver = None  # type: ignore[assignment]

from copilot.core.llm import make_llm
from copilot.core.api_dependencies import verify_internal_api_key
from copilot.core.config import get_settings as get_registry_settings
from copilot.core.database import get_connection_pool, init_db, psycopg_conninfo
from copilot.core.health import router as registry_health_router
from copilot.core.lifecycle import shutdown_backend_runtime, start_backend_runtime
from copilot.agent import build_graph
from copilot.media.routes import create_media_router
from copilot.core.settings import Settings as AgentSettings
from copilot.threads import (
    suggest_thread_title,
    sync_thread_after_run,
)
from copilot.threads.routes import create_threads_router
from copilot.agent.tools import LOCAL_TOOLS, REGISTRY_TOOLS
from copilot.api_keys.router import router as api_keys_router
from copilot.auth.router import router as me_router
from copilot.jobs.active import set_active_job_service
from copilot.jobs.routes import router as jobs_router
from copilot.jobs.service import JobService
from copilot.search.router import router as search_router
from copilot.catalog.router import router as things_router
from copilot.api.wot_runtime import router as wot_runtime_router
from copilot.panels.router import router as panels_router
from copilot.virtual_things.routes import router as virtual_things_router

logger = logging.getLogger(__name__)
EMBED_EPHEMERAL_THREAD_PREFIX = "embed-ephemeral-"

# Module-level references kept alive for the process lifetime.
_agent: LangGraphAGUIAgent | None = None
_graph: Any | None = None
_checkpointer: Any | None = None
_settings: AgentSettings | None = None
_job_service: JobService | None = None
_thread_run_locks: dict[str, asyncio.Lock] = {}
_thread_run_locks_guard = asyncio.Lock()


def _is_embed_ephemeral_thread(thread_id: str | None) -> bool:
    return isinstance(thread_id, str) and thread_id.startswith(EMBED_EPHEMERAL_THREAD_PREFIX)


def _checkpoint_database_url(
    *,
    settings: AgentSettings,
    registry_database_url: str,
) -> str:
    if settings.agent_state_database_url:
        return settings.agent_state_database_url

    return registry_database_url


@asynccontextmanager
async def _checkpoint_saver_context(
    *,
    settings: AgentSettings,
    registry_database_url: str,
):
    database_url = _checkpoint_database_url(
        settings=settings,
        registry_database_url=registry_database_url,
    )
    if AsyncPostgresSaver is None:
        raise RuntimeError(
            "Postgres checkpointing requires langgraph-checkpoint-postgres to be installed"
        )

    async with AsyncPostgresSaver.from_conn_string(
        psycopg_conninfo(database_url)
    ) as postgres_saver:
        await postgres_saver.setup()
        yield postgres_saver


def _log_background_task_exception(
    task: asyncio.Task[None],
    *,
    error_message: str,
) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        logger.warning("%s: task was cancelled", error_message)
    except Exception as exc:
        logger.error("%s: %s", error_message, exc, exc_info=exc)


async def _run_persistence_operation(
    operation: Any,
    *,
    error_message: str,
) -> bool:
    """Run persistence work so cancellation doesn't kill the inner task.

    Returns ``True`` when the caller was cancelled while the operation kept
    running in the background.
    """

    task = asyncio.create_task(operation)
    try:
        await asyncio.shield(task)
        return False
    except asyncio.CancelledError:
        task.add_done_callback(
            lambda finished_task: _log_background_task_exception(
                finished_task,
                error_message=error_message,
            )
        )
        return True
    except Exception:
        logger.exception(error_message)
        return False


async def _finalize_thread_run(thread_id: str | None) -> None:
    if _is_embed_ephemeral_thread(thread_id):
        if thread_id:
            cancelled = await _delete_checkpoint_thread(thread_id)
            if cancelled:
                raise asyncio.CancelledError
        return

    cancelled = await _run_persistence_operation(
        _sync_thread_metadata_after_run(thread_id),
        error_message=f"Failed to sync thread metadata for {thread_id}",
    )

    if cancelled:
        raise asyncio.CancelledError


async def _thread_run_lock(thread_id: str) -> asyncio.Lock:
    async with _thread_run_locks_guard:
        lock = _thread_run_locks.get(thread_id)
        if lock is None:
            lock = asyncio.Lock()
            _thread_run_locks[thread_id] = lock
        return lock


async def _delete_checkpoint_thread(thread_id: str) -> bool:
    if _checkpointer is None:
        return False

    return await _run_persistence_operation(
        _checkpointer.adelete_thread(thread_id),
        error_message=f"Failed to delete checkpoints for {thread_id}",
    )


async def _get_checkpoint_tuple(thread_id: str) -> Any | None:
    if _checkpointer is None:
        return None

    return await _checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})


class _AGUIAgentProxy:
    name = "copilot"

    def clone(self):
        return _AGUIAgentProxy()

    async def run(self, input_data):
        if _agent is None:
            raise RuntimeError("AG-UI agent is not ready")

        thread_id = _request_thread_id(input_data)
        if thread_id:
            lock = await _thread_run_lock(thread_id)
            async with lock:
                try:
                    async for event in _agent.run(input_data):
                        yield event
                finally:
                    await _finalize_thread_run(thread_id)
            return

        try:
            async for event in _agent.run(input_data):
                yield event
        finally:
            await _finalize_thread_run(thread_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent, _graph, _checkpointer, _settings, _job_service

    settings = AgentSettings()
    _settings = settings
    logging.basicConfig(level=settings.log_level)
    await asyncio.to_thread(init_db)

    registry_settings = get_registry_settings()
    connection_pool = get_connection_pool()
    await start_backend_runtime(
        app,
        settings=registry_settings,
        connection_pool=connection_pool,
    )

    try:
        llm = make_llm(settings)

        async with _checkpoint_saver_context(
            settings=settings,
            registry_database_url=registry_settings.DATABASE_URL,
        ) as saver:
            logger.info("Using LangGraph Postgres saver for checkpoints")
            _checkpointer = saver
            checkpointer = _checkpointer
            app.state.checkpointer = checkpointer
            graph = build_graph(
                llm=llm,
                registry_tools=REGISTRY_TOOLS,
                local_tools=LOCAL_TOOLS,
                max_tokens=settings.max_context_tokens,
                checkpointer=checkpointer,
                parallel_tool_calls=settings.parallel_tool_calls,
                vision_enabled=settings.vision_enabled,
            )
            graph = graph.with_config(recursion_limit=settings.recursion_limit)
            _graph = graph
            app.state.graph = graph

            logger.info(
                "Graph created with %d registry tools, model=%s, recursion_limit=%d",
                len(REGISTRY_TOOLS),
                settings.openai_model,
                settings.recursion_limit,
            )

            _agent = LangGraphAGUIAgent(
                name="copilot",
                description="Smart Living Copilot",
                graph=graph,
            )

            app.state.settings = settings
            app.state.agent_settings = settings
            _job_service = JobService(settings)
            await _job_service.start()
            app.state.service = _job_service
            set_active_job_service(_job_service)
            logger.info("Job API started")

            yield
            set_active_job_service(None)
            if _job_service is not None:
                await _job_service.stop()
            app.state.checkpointer = None
    finally:
        await shutdown_backend_runtime(app)


app = FastAPI(title="Smart Living Copilot", lifespan=lifespan)
add_langgraph_fastapi_endpoint(app=app, agent=_AGUIAgentProxy(), path="/ag-ui")
app.include_router(registry_health_router)
app.include_router(me_router)
app.include_router(search_router)
app.include_router(things_router)
app.include_router(api_keys_router)
app.include_router(jobs_router)
app.include_router(wot_runtime_router)
app.include_router(panels_router)
app.include_router(virtual_things_router)


def _current_settings() -> AgentSettings | None:
    return _settings


def _current_checkpointer() -> Any | None:
    return _checkpointer


def _request_thread_id(input_data: Any) -> str | None:
    if isinstance(input_data, dict):
        for key in ("threadId", "thread_id"):
            value = input_data.get(key)
            if isinstance(value, str) and value:
                return value

        configurable = input_data.get("configurable")
        if isinstance(configurable, dict):
            for key in ("threadId", "thread_id"):
                value = configurable.get(key)
                if isinstance(value, str) and value:
                    return value
        return None

    for attr in ("threadId", "thread_id"):
        value = getattr(input_data, attr, None)
        if isinstance(value, str) and value:
            return value

    configurable = getattr(input_data, "configurable", None)
    if isinstance(configurable, dict):
        for key in ("threadId", "thread_id"):
            value = configurable.get(key)
            if isinstance(value, str) and value:
                return value

    return None


async def _sync_thread_metadata_after_run(thread_id: str | None) -> None:
    if not thread_id or _settings is None:
        return

    title = await _suggest_thread_title(thread_id)
    await asyncio.to_thread(
        sync_thread_after_run,
        thread_id,
        suggested_title=title,
    )


async def _suggest_thread_title(thread_id: str) -> str | None:
    state = await _get_checkpoint_tuple(thread_id)
    if state is None or state.checkpoint is None:
        return None

    channel_values = state.checkpoint.get("channel_values", {})
    messages = channel_values.get("messages", [])
    if not isinstance(messages, list):
        return None

    return suggest_thread_title(messages)


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(
    create_media_router(
        get_settings=_current_settings,
        verify_internal_api_key=verify_internal_api_key,
    )
)
app.include_router(
    create_threads_router(
        get_checkpointer=_current_checkpointer,
        verify_internal_api_key=verify_internal_api_key,
    )
)
