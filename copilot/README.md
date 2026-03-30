# Copilot

`copilot` is the Python agent service behind Smart Living Copilot. It exposes a small FastAPI surface, builds a LangGraph-based agent on startup, serves the AG-UI protocol for CopilotKit, and persists thread state in SQLite by LangGraph thread id.

## What This Service Does

- Starts a FastAPI app in [`copilot/server.py`](./copilot/server.py).
- Builds a `LangGraphAGUIAgent` during app lifespan.
- Loads WoT Registry MCP tools through a streamable HTTP MCP client.
- Wires local tools like `run_code` and `get_current_time` into the graph.
- Persists LangGraph checkpoints in SQLite at `AGENT_STATE_DB_PATH`.
- Serves AG-UI events to the frontend through `POST /ag-ui`.
- Deletes LangGraph thread state through `DELETE /threads/{thread_id}`.

## Current API Surface

### `POST /ag-ui`

AG-UI endpoint registered through `add_langgraph_fastapi_endpoint(...)`.

- Used by: `chat-ui /api/copilotkit`
- Input: `RunAgentInput`
- Output: AG-UI SSE stream

### `GET /ag-ui/health`

Health endpoint added by the AG-UI FastAPI helper.

### `GET /health`

Basic service health check.

### `DELETE /threads/{thread_id}`

Deletes LangGraph checkpoint rows for one thread.

- Auth: `Authorization: Bearer <INTERNAL_API_KEY>` when configured
- Deletes from both `writes` and `checkpoints`
- Used by: sidebar thread deletion in `chat-ui`

## High-Level Flow

```text
chat-ui /chat/[chatId]
  -> CopilotKit threadId = chatId
  -> /api/copilotkit
  -> LangGraphHttpAgent
  -> copilot POST /ag-ui
  -> LangGraphAGUIAgent
  -> compiled graph
  -> MCP tools and local tools
```

The same `chatId` becomes the LangGraph `thread_id`, so thread continuity is keyed consistently between the frontend route and the backend checkpointer.

## LangGraph Agent Architecture

The graph is assembled in [`copilot/graph/builder.py`](./copilot/graph/builder.py).

### State

```python
class CopilotState(CopilotKitState):
    messages: Annotated[list[AnyMessage], add_messages]
    intent: str
```

### Graph Shape

```text
START
  -> router
     -> respond -> respond_tools -> respond -> END
     -> control_llm -> control_tools -> control_llm -> END
     -> analysis_llm -> analysis_tools -> analysis_llm -> END
```

### Branches

- `chat`: lightweight responses with `get_current_time`
- `control`: device control with discovery, schema inspection, and runtime MCP tools
- `analysis`: data analysis with discovery/inspect MCP tools and `run_code`

## Tool Partitioning

Tool grouping lives in [`copilot/graph/tool_groups.py`](./copilot/graph/tool_groups.py).

| Group | Tools | Used by |
|-------|-------|---------|
| `discovery` | `things_list`, `things_search` | control, analysis |
| `inspect` | `things_get`, `wot_get_action`, `wot_get_property`, `wot_get_event` | control, analysis |
| `runtime` | `wot_invoke_action`, `wot_read_property`, `wot_write_property`, `wot_observe_property`, `wot_subscribe_event`, `wot_remove_subscription` | control |

Local tools are grouped separately:

- [`get_current_time`](./copilot/tools/get_current_time.py)
- [`run_code`](./copilot/tools/run_code.py)

## Persistence

### LangGraph Thread State

- Backend: SQLite through `AsyncSqliteSaver`
- Path: `AGENT_STATE_DB_PATH`
- Key: `thread_id`

### Code Execution State

- Lives in the separate `code-executor` service
- Uses the same chat/thread id for session continuity
- Is cleaned up independently from the LangGraph checkpoint database

## Important Files

- [`copilot/server.py`](./copilot/server.py): FastAPI app, AG-UI endpoint registration, thread deletion
- [`copilot/agent.py`](./copilot/agent.py): model factory, MCP client setup, MCP tool loading
- [`copilot/graph/builder.py`](./copilot/graph/builder.py): graph assembly
- [`copilot/graph/nodes.py`](./copilot/graph/nodes.py): node behavior and state shaping
- [`copilot/graph/tool_groups.py`](./copilot/graph/tool_groups.py): explicit tool grouping
- [`copilot/prompts`](./copilot/prompts): system prompts by branch
- [`copilot/few_shots`](./copilot/few_shots): branch-specific few-shot examples for analysis and control
- [`copilot/tools/run_code.py`](./copilot/tools/run_code.py): bridge to the Code Executor

## Development

### With Docker Compose

```bash
docker compose up -d copilot
docker compose exec copilot sh -lc "cd /app && python -m unittest tests.test_server tests.test_tool_groups"
```

The dev override mounts:

- `./copilot/copilot -> /app/copilot`
- `./copilot/tests -> /app/tests`

and starts Uvicorn with reload.

### Directly

```bash
cd copilot
pip install -e ".[dev]"
uvicorn copilot.server:app --host 0.0.0.0 --port 8123 --reload
```

## Environment Variables

Defined in [`copilot/models/settings.py`](./copilot/models/settings.py):

- `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`
- `WOT_REGISTRY_URL`, `WOT_REGISTRY_TOKEN`
- `CODE_EXECUTOR_URL`, `CODE_EXECUTOR_TIMEOUT_SECONDS`
- `INTERNAL_API_KEY`
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`
- `AGENT_STATE_DB_PATH`
- `MAX_CONTEXT_TOKENS`
- `LOG_LEVEL`

## Contributor Rules Of Thumb

- Keep AG-UI transport concerns in the framework helper, not hand-written routes.
- Keep `threadId` aligned with the frontend `chatId`.
- Treat `DELETE /threads/{thread_id}` as part of the user-facing delete flow, not an internal afterthought.
- If the UI needs more thread metadata, add it to the sidebar index in `chat-ui` before changing the backend checkpoint model.
