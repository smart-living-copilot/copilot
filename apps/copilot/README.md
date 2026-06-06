# Copilot

`copilot` is the Python agent service behind Smart Living Copilot. It builds the LangGraph assistant, owns the Thing registry and automation job backend, persists conversation and registry state, and provides worker roles used by the stack.

## What This Service Owns

- LangGraph agent assembly, routing, prompts, and tool binding.
- Backend API composition for chat transport, threads, Things, credentials, API keys, jobs, media, and speech.
- Postgres persistence for LangGraph checkpoints, thread metadata, Thing registry data, credentials, API keys, search vectors, and jobs.
- Redis-backed job events and scheduling coordination through Taskiq.
- LiveKit agent worker integration for local voice and camera-assisted sessions.
- The worker entrypoints for job execution, scheduling, Thing indexing, and LiveKit.

It is intended to run on an internal network behind `ui`.

## Runtime Shape

```text
ui
  -> copilot FastAPI app
     -> LangGraph agent
     -> code-executor for run_code
     -> wot-runtime for Thing operations
     -> Postgres / Valkey
```

The frontend `chatId`, CopilotKit `threadId`, LangGraph `thread_id`, and code-executor session id are intentionally the same value so chat continuity stays aligned across services.

## Agent Architecture

The graph is assembled in [`src/copilot/agent/builder.py`](./src/copilot/agent/builder.py). A router selects a branch, then the selected branch alternates between an LLM node and its allowed tools.

```text
START
  -> router
     -> respond -> respond_tools -> respond -> END
     -> control_llm -> control_tools -> control_llm -> END
     -> analysis_llm -> analysis_tools -> analysis_llm -> END
     -> jobs_llm -> jobs_tools -> jobs_llm -> END
```

- `chat`: lightweight conversational responses.
- `control`: device discovery and control.
- `analysis`: device/data analysis plus Python execution.
- `jobs`: automation job creation, inspection, debugging, manual runs, and deletion.

Prompts live in [`src/copilot/agent/prompts`](./src/copilot/agent/prompts). Tool grouping lives in [`src/copilot/agent/tool_groups.py`](./src/copilot/agent/tool_groups.py).

## Jobs And Live Media

Automation jobs use the same graph and persistence model as normal conversations, with hidden per-job checkpoint threads when a job needs user input. The Docker stack runs separate `job-worker` and `job-scheduler` processes from the same image.

Live voice uses a self-hosted LiveKit Server plus the `copilot livekit-agent` worker. The worker handles realtime media, speech-to-text, text-to-speech, interruption handling, transcription forwarding, and the bridge back into the LangGraph assistant.

## Persistence And Migrations

The application schema is owned by Alembic migrations in [`migrations`](./migrations). App startup calls `alembic upgrade head`, so API, worker, LiveKit, and indexer processes share the same schema path.

Run migrations manually from `apps/copilot` when needed:

```bash
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

LangGraph checkpoints use `AGENT_STATE_DATABASE_URL` when set, otherwise `REGISTRY_DATABASE_URL`. Keep `SEARCH_VECTOR_DIMENSIONS` stable for an existing database because the pgvector column is migrated with that dimension.

## Development

### With Docker Compose

```bash
docker compose up -d copilot
docker compose exec copilot sh -lc "cd /app && python -m pytest tests"
```

The dev override builds the local image, bind-mounts source, migrations, and tests, and runs the API with reload.

### Directly

```bash
cd apps/copilot
pip install -e ".[dev]"
copilot serve --reload
```

Other local process roles:

```bash
copilot job-worker
copilot job-scheduler
copilot thing-indexer
copilot livekit-agent start
```

Container-backed integration tests start disposable pgvector Postgres and Valkey services:

```bash
.venv/bin/python -m pip install -e "apps/copilot[test]"
.venv/bin/python -m pytest -c apps/copilot/pyproject.toml \
  apps/copilot/tests/integration -m integration
```

## Environment

The root [`.env.example`](../../.env.example) documents required and optional settings. Runtime settings are defined in [`src/copilot/core/settings.py`](./src/copilot/core/settings.py). [`src/copilot/core/config.py`](./src/copilot/core/config.py) keeps the legacy cached `get_settings()` import path.

Common groups:

- LLM, embedding, and vision model settings.
- Shared internal API keys and registry tokens.
- Postgres, pgvector, and LangGraph checkpoint configuration.
- Redis, Taskiq jobs, WoT runtime, and event stream settings.
- LiveKit, speech-to-text, and text-to-speech settings.
- Code-executor URL, timeout, and retry settings.

## Security Boundary

`copilot` assumes an internal-service deployment model. Public traffic should terminate at `ui`, with `copilot`, `code-executor`, `wot-runtime`, Postgres, and Valkey kept off the public internet.

Shared internal credentials protect service-to-service calls when configured. Registry API keys are intended for registry management and search, not direct unrestricted device control.

## Important Files

- [`src/copilot/api/main.py`](./src/copilot/api/main.py): FastAPI app composition.
- [`src/copilot/cli.py`](./src/copilot/cli.py): process role entrypoint.
- [`src/copilot/agent`](./src/copilot/agent): graph builder, nodes, prompts, tools, and voice adapter.
- [`src/copilot/catalog`](./src/copilot/catalog): Thing registry, credentials, validation, and event outbox.
- [`src/copilot/jobs`](./src/copilot/jobs): job definitions, runs, scheduler integration, records, events, and stores.
- [`src/copilot/media`](./src/copilot/media): LiveKit token, dispatch, and media helpers.
- [`src/copilot/threads`](./src/copilot/threads): thread metadata, message loading, titles, and routes.
- [`src/copilot/search`](./src/copilot/search): embedding and vector search for Things.
- [`src/copilot/thing_indexer`](./src/copilot/thing_indexer): Thing indexing worker.
- [`src/copilot/workers`](./src/copilot/workers): process role implementations.
- [`migrations`](./migrations): Alembic migrations.

## Contributor Notes

- Keep AG-UI transport concerns in the framework helper where possible.
- Keep thread ids aligned across UI, LangGraph, and code execution.
- Keep prompts concise and prefer clearer tool boundaries over longer instructions.
- Treat schema changes as migration changes and verify with `alembic check`.
- Keep direct device/runtime access behind internal services.
