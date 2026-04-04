"""FastAPI + AG-UI entrypoint for the Smart Living Copilot."""

import logging
from contextlib import asynccontextmanager

import aiosqlite
from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from copilotkit import LangGraphAGUIAgent
from fastapi import FastAPI, HTTPException, Request
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from copilot.agent import _load_mcp_tools, _make_llm, _make_mcp_client
from copilot.graph import build_graph
from copilot.models import Settings
from copilot.tools import AVAILABLE_TOOLS

logger = logging.getLogger(__name__)

# Module-level references kept alive for the process lifetime.
_mcp_client = None
_agent: LangGraphAGUIAgent | None = None
_settings: Settings | None = None


class _AGUIAgentProxy:
    name = "copilot"

    def clone(self):
        return _AGUIAgentProxy()

    async def run(self, input_data):
        if _agent is None:
            raise RuntimeError("AG-UI agent is not ready")

        async for event in _agent.run(input_data):
            yield event


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _mcp_client, _agent, _settings

    settings = Settings()
    _settings = settings
    logging.basicConfig(level=settings.log_level)

    llm = _make_llm(settings)

    _mcp_client = _make_mcp_client(settings)
    mcp_tools = await _load_mcp_tools(_mcp_client)

    async with AsyncSqliteSaver.from_conn_string(settings.agent_state_db_path) as checkpointer:
        graph = build_graph(
            llm=llm,
            mcp_tools=mcp_tools,
            local_tools=AVAILABLE_TOOLS,
            max_tokens=settings.max_context_tokens,
            checkpointer=checkpointer,
            parallel_tool_calls=settings.parallel_tool_calls,
        )

        logger.info(
            "Graph created with %d MCP tools, model=%s",
            len(mcp_tools),
            settings.openai_model,
        )

        _agent = LangGraphAGUIAgent(
            name="copilot",
            description="Smart Living Copilot",
            graph=graph,
        )

        yield


app = FastAPI(title="Smart Living Copilot", lifespan=lifespan)
add_langgraph_fastapi_endpoint(app=app, agent=_AGUIAgentProxy(), path="/ag-ui")


def _verify_internal_api_key(request: Request) -> None:
    if not _settings or not _settings.internal_api_key:
        return

    auth_header = request.headers.get("authorization", "")
    expected = f"Bearer {_settings.internal_api_key}"
    if auth_header != expected:
        raise HTTPException(status_code=401, detail="Invalid internal API key")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.delete("/threads/{thread_id}")
async def delete_thread(thread_id: str, request: Request):
    _verify_internal_api_key(request)

    if _settings is None:
        raise HTTPException(status_code=503, detail="Settings not loaded")

    async with aiosqlite.connect(_settings.agent_state_db_path) as db:
        writes_cursor = await db.execute(
            "DELETE FROM writes WHERE thread_id = ?",
            (thread_id,),
        )
        checkpoints_cursor = await db.execute(
            "DELETE FROM checkpoints WHERE thread_id = ?",
            (thread_id,),
        )
        await db.commit()

    return {
        "ok": True,
        "thread_id": thread_id,
        "deleted_writes": writes_cursor.rowcount,
        "deleted_checkpoints": checkpoints_cursor.rowcount,
    }
