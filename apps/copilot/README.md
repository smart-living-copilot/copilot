# Copilot

`copilot` is the Python agent service behind Smart Living Copilot. It is an internal FastAPI service that builds a LangGraph-based assistant on startup, serves the AG-UI protocol to CopilotKit, and persists both LangGraph thread state and sidebar thread metadata in Postgres.

## Current Role In The Stack

- `ui` owns the browser experience and the authenticated edge.
- `copilot` owns agent orchestration, prompts, tool use, the WoT registry API, LangGraph checkpoint state, and thread metadata.
- `code-executor` runs stateful Python for the `run_code` tool.
- `job-worker` and `job-scheduler` run automation jobs through Taskiq.

At runtime, the browser talks to `ui`, `ui` proxies agent traffic to `copilot`, and `copilot` uses local LangGraph tools for registry/runtime access and `code-executor` for Python execution. `copilot` owns the job API and result SSE stream, `job-worker` executes jobs and bridges WoT runtime events into Taskiq jobs, and `job-scheduler` sends time-triggered runs. Prompt jobs use a stateless background graph and store results on the job record instead of visible chat threads.

## Request Lifecycle

```text
/chat/[chatId] in ui
  -> CopilotKit threadId = chatId
  -> ui /api/copilotkit
  -> copilot POST /ag-ui
  -> LangGraphAGUIAgent
  -> router branch
  -> registry/runtime tools and local tools
  -> AG-UI stream back to ui
```

The frontend `chatId`, CopilotKit `threadId`, LangGraph `thread_id`, and `run_code` session id are intentionally the same value so chat continuity stays aligned across services.

## API Surface

### `POST /ag-ui`

AG-UI endpoint registered through `add_langgraph_fastapi_endpoint(...)`.

- Used by: `ui /api/copilotkit`
- Input: CopilotKit `RunAgentInput`
- Output: AG-UI SSE stream
- Auth: none in-app today; expected to stay on the internal network behind `ui`

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
- Used by: thread deletion flow in `ui`

## Graph Architecture

The graph is assembled in [`copilot/agent/builder.py`](./src/copilot/agent/builder.py).

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

Tool grouping lives in [`copilot/agent/tool_groups.py`](./src/copilot/agent/tool_groups.py).

| Group | Tools | Used by |
|-------|-------|---------|
| `discovery` | `things_list`, `things_search` | control, analysis |
| `inspect` | `things_get`, `wot_get_action`, `wot_get_property`, `wot_get_event` | control, analysis |
| `runtime_read` | `wot_read_property`, `wot_observe_property` | analysis |
| `runtime` | `wot_invoke_action`, `wot_write_property`, `wot_subscribe_event`, `wot_remove_subscription`, plus the read tools above | control |

Local tools are grouped separately:

- [`get_current_time`](./src/copilot/agent/tools/get_current_time.py)
- [`run_code`](./src/copilot/agent/tools/run_code.py)
- [`create_job`, `create_analysis_job`, `list_jobs`, `run_job_now`, `delete_job`](./src/copilot/agent/tools/job_scheduler.py)
- registry/runtime tools live in [`copilot/agent/tools/wot_registry.py`](./src/copilot/agent/tools/wot_registry.py)

## Prompts And Few-Shots

- Branch prompts live in [`copilot/agent/prompts`](./src/copilot/agent/prompts).
- Analysis examples live in [`copilot/few_shots/analysis.py`](./src/copilot/few_shots/analysis.py).
- Control examples live in [`copilot/few_shots/control.py`](./src/copilot/few_shots/control.py).
- Registry/runtime tools are grouped explicitly in [`copilot/agent/tool_groups.py`](./src/copilot/agent/tool_groups.py).

Current behavior worth knowing:

- tool calls are bound with `parallel_tool_calls=False`
- analysis gets a current-time block injected into its system prompt
- prompts are shaped and trimmed in [`copilot/agent/nodes.py`](./src/copilot/agent/nodes.py) before they are fed to the model

## `run_code` Integration

`run_code` is a local LangChain tool implemented in [`copilot/agent/tools/run_code.py`](./src/copilot/agent/tools/run_code.py).

Current flow:

1. The model calls `run_code(...)`.
2. `copilot` sends `POST /execute` to `code-executor` with `session_id = thread_id`.
3. `code-executor` returns `stdout`, `images`, and `plotly`.
4. `copilot` normalizes that into structured tool output with `stdout` plus `artifacts`.
5. `ui` renders those artifacts below the tool call.

This is the current structured-artifact flow. The older marker-based `[IMAGE:...]` / `[CHART:...]` approach is no longer used.

## Persistence

### LangGraph State

- backend: Postgres through `AsyncPostgresSaver` by default
- database URL: `AGENT_STATE_DATABASE_URL`, falling back to `REGISTRY_DATABASE_URL`
- key: `thread_id`

Thread metadata, registry tables, API keys, credentials, event outbox rows, and
automation jobs share the SQLAlchemy database configured by `REGISTRY_DATABASE_URL`.

### Code Execution State

- lives in the separate `code-executor` service
- uses the same thread id for session continuity
- is cleaned up independently through `DELETE /sessions/{session_id}` in `code-executor`

## Security Boundary

This service currently assumes an internal-service deployment model.

- `POST /ag-ui` is not protected by an in-app API key today
- `DELETE /threads/{thread_id}` is protected by `INTERNAL_API_KEY` when configured
- the intended boundary is: public traffic terminates at `ui`, while `copilot` stays on the internal network

If the stack is deployed publicly through Kubernetes ingress, keep `copilot` internal-only and let ingress or `ui` enforce user authentication.

External API keys are intended for registry management, not direct device
control. The currently valid API-key scopes are:

- `things:read`, `things:write`, `things:delete`
- `search:read`
- `credentials:read`, `credentials:write`
- `keys:manage`

`GET /api/credentials/{thing_id}` returns credential metadata only. Raw
credential payloads are only exposed through the service-only
`GET /api/runtime/secrets` endpoint used by `wot-runtime`.

## Development

### With Docker Compose

```bash
docker compose up -d copilot
docker compose exec copilot sh -lc "cd /app && python -m pytest tests"
```

The dev override:

- builds the local image from [`Dockerfile`](./Dockerfile)
- mounts `apps/copilot/src -> /app/src`
- mounts `apps/copilot/tests -> /app/tests`
- runs `copilot serve --reload`

### Directly

```bash
cd apps/copilot
pip install -e ".[dev]"
copilot serve --reload
```

Postgres-backed tests require `COPILOT_TEST_DATABASE_URL` to point at a
disposable Postgres database. Tests that need database access are skipped when
that variable is not set.

## Environment Variables

Defined in [`src/copilot/core/settings.py`](./src/copilot/core/settings.py):

- `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`
- `CODE_EXECUTOR_URL`, `CODE_EXECUTOR_TIMEOUT_SECONDS`
- `JOB_RUNNER_URL`, `JOB_RUNNER_TIMEOUT_SECONDS` (the job tools call copilot's own `/jobs` API)
- `JOBS_ENABLED`, `JOB_TASK_TIMEOUT_SECONDS`, `JOBS_RUN_EVENTS_STREAM`, `JOB_SCHEDULER_UPDATE_INTERVAL_SECONDS`
- `REDIS_URL`, `WOT_RUNTIME_URL`, `WOT_RUNTIME_API_TOKEN`, `WOT_RUNTIME_STREAM`
- `JOBS_EVENTS_GROUP`, `JOBS_EVENTS_CONSUMER`, `JOBS_STREAM_BATCH_SIZE`, `JOBS_STREAM_POLL_BLOCK_MS`, `JOBS_STREAM_CLAIM_IDLE_MS`
- `INTERNAL_API_KEY`
- `REGISTRY_DATABASE_URL`, `AGENT_STATE_DATABASE_URL`
- `MAX_CONTEXT_TOKENS`
- `LOG_LEVEL`
- `MEDIA_RTC_CONFIGURATION`, `MEDIA_SERVER_RTC_CONFIGURATION`
- `MEDIA_ICE_GATHER_TIMEOUT_MS`
- `STT_ENABLED`, `STT_TRANSCRIPTIONS_URL`, `STT_MODEL`, `STT_API_KEY`
- `STT_LANGUAGE`, `STT_TIMEOUT_SECONDS`, `STT_SUBMIT_TO_CHAT`
- `VAD_THRESHOLD`, `VAD_MIN_SPEECH_MS`, `VAD_MIN_SILENCE_MS`
- `VAD_SPEECH_PAD_MS`, `VAD_MAX_UTTERANCE_MS`
- `TTS_ENABLED`, `TTS_SPEECH_URL`, `TTS_MODEL`, `TTS_VOICE`
- `TTS_API_KEY`, `TTS_RESPONSE_FORMAT`, `TTS_SPEED`, `TTS_TIMEOUT_SECONDS`

Live media speech-to-text uses backend Silero VAD and an OpenAI-compatible
`/v1/audio/transcriptions` endpoint configured with `STT_TRANSCRIPTIONS_URL`.
Assistant speech playback uses an external OpenAI-compatible `/v1/audio/speech`
endpoint and returns audio over WebRTC.
For local Kokoro-FastAPI playback, start `docker compose --profile tts up`, set
`TTS_ENABLED=true`, and choose a `TTS_VOICE` returned by `GET /v1/audio/voices`.

Live media WebRTC setup is controlled by:

- `MEDIA_RTC_CONFIGURATION`: JSON passed to the browser `RTCPeerConnection`.
- `MEDIA_SERVER_RTC_CONFIGURATION`: JSON passed to the backend aiortc peer.
- `MEDIA_ICE_GATHER_TIMEOUT_MS`: browser-side non-trickle ICE gather wait before the offer is sent.

For production, configure explicit STUN/TURN servers in both RTC configuration
values and make sure UDP/TURN traffic reaches the media backend. For local
development, keep `MEDIA_ICE_GATHER_TIMEOUT_MS` low, such as `750`, so Docker
bridge candidate gathering does not add several seconds before the offer is sent.

Also defined today but not currently wired into the graph execution path:

- `MAX_ITERATIONS`
- `RECURSION_LIMIT`

## Important Files

- [`src/copilot/api/main.py`](./src/copilot/api/main.py): unified FastAPI app composition and AG-UI endpoint registration
- [`src/copilot/catalog`](./src/copilot/catalog): Thing catalog, credentials, validation, and event outbox
- [`src/copilot/thing_indexer`](./src/copilot/thing_indexer): Thing search indexing domain logic
- [`src/copilot/workers`](./src/copilot/workers): process role entrypoints for jobs, scheduler, and indexing
- [`src/copilot/media`](./src/copilot/media): browser media ingress, speech pipeline, live camera helpers, and media routes
- [`src/copilot/threads`](./src/copilot/threads): thread metadata storage, title helpers, and thread routes
- [`src/copilot/core/llm.py`](./src/copilot/core/llm.py): model factory
- [`src/copilot/agent/builder.py`](./src/copilot/agent/builder.py): graph assembly
- [`src/copilot/agent/nodes.py`](./src/copilot/agent/nodes.py): node behavior and prompt shaping
- [`src/copilot/agent/tool_groups.py`](./src/copilot/agent/tool_groups.py): explicit tool grouping
- [`src/copilot/agent/prompts`](./src/copilot/agent/prompts): system prompts by branch
- [`src/copilot/agent/tools/run_code.py`](./src/copilot/agent/tools/run_code.py): bridge to `code-executor`
- [`src/copilot/agent/tools/job_scheduler.py`](./src/copilot/agent/tools/job_scheduler.py): agent tools for the job API
- [`src/copilot/jobs`](./src/copilot/jobs): job CRUD routes, Taskiq task execution, Postgres schedule source, WoT event consumer, and Redis-backed run events

## Contributor Notes

- Keep AG-UI transport concerns in the framework helper, not hand-written SSE routes.
- Keep `threadId`, `chatId`, LangGraph `thread_id`, and `run_code` session ids aligned.
- Treat `DELETE /threads/{thread_id}` as part of the user-facing delete flow, not optional cleanup.
- Prefer reducing tool ambiguity and adding examples over making prompts longer.
