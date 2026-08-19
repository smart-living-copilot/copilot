"""FastAPI + AG-UI entrypoint for WoTBot."""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from copilotkit import LangGraphAGUIAgent
from fastapi import FastAPI

try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
except ImportError:  # pragma: no cover - exercised when optional dep is absent locally.
    AsyncPostgresSaver = None  # type: ignore[assignment]

from wotbot.agent import build_graph
from wotbot.agent.tools import LOCAL_TOOLS, REGISTRY_TOOLS
from wotbot.api.wot_runtime import router as wot_runtime_router
from wotbot.api_keys.router import router as api_keys_router
from wotbot.auth.router import router as me_router
from wotbot.catalog.router import router as things_router
from wotbot.core.api_dependencies import verify_internal_api_key
from wotbot.core.agui_runtime import AguiRuntime
from wotbot.core.config import get_settings as get_registry_settings
from wotbot.core.database import get_connection_pool, init_db, psycopg_conninfo
from wotbot.core.health import router as registry_health_router
from wotbot.core.lifecycle import shutdown_backend_runtime, start_backend_runtime
from wotbot.core.llm import make_llm
from wotbot.core.settings import Settings as AgentSettings
from wotbot.jobs.active import set_active_job_service
from wotbot.jobs.routes import router as jobs_router
from wotbot.jobs.service import JobService
from wotbot.media.routes import create_media_router
from wotbot.panels.router import router as panels_router
from wotbot.search.router import router as search_router
from wotbot.threads.routes import create_threads_router
from wotbot.virtual_things.routes import router as virtual_things_router

logger = logging.getLogger(__name__)
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

agui_runtime = AguiRuntime()


def _checkpoint_database_url(
    *,
    settings: AgentSettings,
    registry_database_url: str,
) -> str:
    if settings.agent_state_database_url:
        return settings.agent_state_database_url

    return registry_database_url


def configure_logging(log_level: str) -> None:
    """Configure process logging even when uvicorn installed handlers first."""
    logging.basicConfig(level=log_level, format=LOG_FORMAT, force=True)
    for logger_name in (
        "wotbot",
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        # Surface the LLM/provider call path so upstream errors (e.g. a
        # context-length 4xx from OpenRouter) are visible at DEBUG instead of
        # vanishing into an abrupt stream close.
        "httpx",
        "openai",
        "langgraph",
        "langchain",
        "ag_ui_langgraph",
    ):
        logging.getLogger(logger_name).setLevel(log_level)


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = AgentSettings()
    agui_runtime.clear_request_state()
    agui_runtime.configure(settings=settings)
    configure_logging(settings.log_level)
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
            checkpointer = saver
            agui_runtime.configure(settings=settings, checkpointer=checkpointer)
            app.state.checkpointer = checkpointer
            graph = build_graph(
                llm=llm,
                registry_tools=REGISTRY_TOOLS,
                local_tools=LOCAL_TOOLS,
                max_tokens=settings.max_context_tokens,
                checkpointer=checkpointer,
                parallel_tool_calls=settings.parallel_tool_calls,
                vision_enabled=settings.vision_enabled,
                handoff_enabled=settings.agent_handoff_enabled,
                reasoning_effort=(
                    settings.reasoning_effort if settings.reasoning_effort.enabled else None
                ),
            )
            graph = graph.with_config(recursion_limit=settings.recursion_limit)
            app.state.graph = graph

            logger.info(
                "Graph created with %d registry tools, model=%s, recursion_limit=%d",
                len(REGISTRY_TOOLS),
                settings.openai_model,
                settings.recursion_limit,
            )

            # LangGraphAGUIAgent runs the graph via astream_events with the
            # config passed here, which overrides the graph's bound config — so
            # recursion_limit must be forwarded explicitly or it falls back to
            # langgraph's default of 25 (surfaces as GraphRecursionError).
            agent = LangGraphAGUIAgent(
                name="wotbot",
                description="WoTBot",
                graph=graph,
                config={"recursion_limit": settings.recursion_limit},
            )
            agui_runtime.configure(
                settings=settings,
                checkpointer=checkpointer,
                agent=agent,
            )

            app.state.settings = settings
            app.state.agent_settings = settings
            job_service = JobService(settings)
            await job_service.start()
            app.state.service = job_service
            set_active_job_service(job_service)
            logger.info("Job API started")

            yield
            set_active_job_service(None)
            await job_service.stop()
            app.state.checkpointer = None
            agui_runtime.clear_request_state()
    finally:
        await shutdown_backend_runtime(app)


app = FastAPI(title="WoTBot", lifespan=lifespan)
agui_runtime.register_endpoint(app, path="/ag-ui")
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
    return agui_runtime.current_settings()


def _current_checkpointer() -> Any | None:
    return agui_runtime.current_checkpointer()


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
