# Copilot

`copilot` is the Python agent service behind Smart Living Copilot. It is an internal FastAPI service that builds a LangGraph-based assistant on startup, serves the AG-UI protocol to CopilotKit, and persists both LangGraph thread state and sidebar thread metadata in SQLite.

## Current Role In The Stack

- `chat-ui` owns the browser experience and the authenticated edge.
- `copilot` owns agent orchestration, prompts, tool use, LangGraph checkpoint state, and thread metadata.
- `code-executor` runs stateful Python for the `run_code` tool.
- `wot-registry` provides discovery, schema inspection, and runtime WoT actions through MCP and HTTP APIs.

At runtime, the browser talks to `chat-ui`, `chat-ui` proxies agent traffic to `copilot`, and `copilot` talks to MCP tools and `code-executor`.

## Request Lifecycle

```text
/chat/[chatId] in chat-ui
  -> CopilotKit threadId = chatId
  -> chat-ui /api/copilotkit
  -> copilot POST /ag-ui
  -> LangGraphAGUIAgent
  -> router branch
  -> MCP tools and local tools
  -> AG-UI stream back to chat-ui
```

The frontend `chatId`, CopilotKit `threadId`, LangGraph `thread_id`, and `run_code` session id are intentionally the same value so chat continuity stays aligned across services.

## API Surface

### `POST /ag-ui`

AG-UI endpoint registered through `add_langgraph_fastapi_endpoint(...)`.

- Used by: `chat-ui /api/copilotkit`
- Input: CopilotKit `RunAgentInput`
- Output: AG-UI SSE stream
- Auth: none in-app today; expected to stay on the internal network behind `chat-ui`

### `GET /ag-ui/health`

Health endpoint added by the AG-UI FastAPI helper.

### `GET /health`

Basic service health check.

### `GET /threads`

Lists thread metadata for the sidebar.

### `POST /threads`

Creates a new thread metadata row and returns the generated thread id.

### `PATCH /threads/{thread_id}`

Updates thread metadata such as the title.

### `GET /threads/{thread_id}`

Returns one thread record together with its persisted messages.

### `DELETE /threads/{thread_id}`

Deletes LangGraph checkpoint rows and thread metadata for one thread.

- Auth: `Authorization: Bearer <INTERNAL_API_KEY>` when configured
- Deletes from both `writes` and `checkpoints`
- Used by: thread deletion flow in `chat-ui`

## Graph Architecture

The graph is assembled in [`copilot/graph/builder.py`](./copilot/graph/builder.py).

### State

```python
class CopilotState(CopilotKitState):
    intent: str = ""
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

- `chat`: lightweight conversational responses, with `get_current_time`
- `control`: device control flows with discovery, schema inspection, and runtime write/read tools
- `analysis`: device/data analysis with discovery/inspection tools plus `run_code`

### Tool Grouping

Tool grouping lives in [`copilot/graph/tool_groups.py`](./copilot/graph/tool_groups.py).

| Group | Tools | Used by |
|-------|-------|---------|
| `discovery` | `things_list`, `things_search` | control, analysis |
| `inspect` | `things_get`, `wot_get_action`, `wot_get_property`, `wot_get_event` | control, analysis |
| `runtime_read` | `wot_read_property`, `wot_observe_property` | analysis |
| `runtime` | `wot_invoke_action`, `wot_write_property`, `wot_subscribe_event`, `wot_remove_subscription`, plus the read tools above | control |

Local tools are grouped separately:

- [`get_current_time`](./copilot/tools/get_current_time.py)
- [`run_code`](./copilot/tools/run_code.py)

## Prompts And Few-Shots

- Branch prompts live in [`copilot/prompts`](./copilot/prompts).
- Analysis examples live in [`copilot/few_shots/analysis.py`](./copilot/few_shots/analysis.py).
- Control examples live in [`copilot/few_shots/control.py`](./copilot/few_shots/control.py).
- MCP tool descriptions are shortened in [`copilot/agent.py`](./copilot/agent.py) to make tool choice easier for smaller models.

Current behavior worth knowing:

- tool calls are bound with `parallel_tool_calls=False`
- analysis gets a current-time block injected into its system prompt
- large tool responses are truncated in [`copilot/graph/nodes.py`](./copilot/graph/nodes.py) before they are fed back to the model

## `run_code` Integration

`run_code` is a local LangChain tool implemented in [`copilot/tools/run_code.py`](./copilot/tools/run_code.py).

Current flow:

1. The model calls `run_code(...)`.
2. `copilot` sends `POST /execute` to `code-executor` with `session_id = thread_id`.
3. `code-executor` returns `stdout`, `images`, and `plotly`.
4. `copilot` normalizes that into structured tool output with `stdout` plus `artifacts`.
5. `chat-ui` renders those artifacts below the tool call.

This is the current structured-artifact flow. The older marker-based `[IMAGE:...]` / `[CHART:...]` approach is no longer used.

## Persistence

### LangGraph State

- backend: SQLite through `AsyncSqliteSaver`
- path: `AGENT_STATE_DB_PATH`
- key: `thread_id`

### Code Execution State

- lives in the separate `code-executor` service
- uses the same thread id for session continuity
- is cleaned up independently through `DELETE /sessions/{session_id}` in `code-executor`

## Security Boundary

This service currently assumes an internal-service deployment model.

- `POST /ag-ui` is not protected by an in-app API key today
- `DELETE /threads/{thread_id}` is protected by `INTERNAL_API_KEY` when configured
- the intended boundary is: public traffic terminates at `chat-ui`, while `copilot` stays on the internal network

If the stack is deployed publicly through Kubernetes ingress, keep `copilot` internal-only and let ingress or `chat-ui` enforce user authentication.

## Development

### With Docker Compose

```bash
docker compose up -d copilot
docker compose exec copilot sh -lc "cd /app && python -m unittest tests.test_server tests.test_tool_groups"
```

The dev override:

- builds the local image from [`Dockerfile`](./Dockerfile)
- mounts `./copilot/copilot -> /app/copilot`
- mounts `./copilot/tests -> /app/tests`
- runs Uvicorn with reload

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
- `WOT_REGISTRY_TIMEOUT_SECONDS`, `WOT_REGISTRY_SSE_READ_TIMEOUT_SECONDS`
- `CODE_EXECUTOR_URL`, `CODE_EXECUTOR_TIMEOUT_SECONDS`
- `INTERNAL_API_KEY`
- `AGENT_STATE_DB_PATH`
- `MAX_CONTEXT_TOKENS`
- `LOG_LEVEL`

Also defined today but not currently wired into the graph execution path:

- `MAX_ITERATIONS`
- `RECURSION_LIMIT`

## Important Files

- [`copilot/server.py`](./copilot/server.py): FastAPI app, AG-UI endpoint registration, thread deletion
- [`copilot/agent.py`](./copilot/agent.py): model factory, MCP client setup, MCP tool loading
- [`copilot/graph/builder.py`](./copilot/graph/builder.py): graph assembly
- [`copilot/graph/nodes.py`](./copilot/graph/nodes.py): node behavior, prompt shaping, tool truncation
- [`copilot/graph/tool_groups.py`](./copilot/graph/tool_groups.py): explicit tool grouping
- [`copilot/prompts`](./copilot/prompts): system prompts by branch
- [`copilot/few_shots`](./copilot/few_shots): branch-specific examples
- [`copilot/tools/run_code.py`](./copilot/tools/run_code.py): bridge to `code-executor`

## Contributor Notes

- Keep AG-UI transport concerns in the framework helper, not hand-written SSE routes.
- Keep `threadId`, `chatId`, LangGraph `thread_id`, and `run_code` session ids aligned.
- Treat `DELETE /threads/{thread_id}` as part of the user-facing delete flow, not optional cleanup.
- Prefer reducing tool ambiguity and adding examples over making prompts longer.
