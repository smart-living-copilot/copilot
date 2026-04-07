# Code Executor

`code-executor` is the internal Python execution service used by Smart Living Copilot's `run_code` tool. It executes Python snippets in a long-lived worker process per chat thread, captures text output and chart/image artifacts, and returns a compact JSON response back to `copilot`.

## Current Role In The Stack

- `chat-ui` renders charts and images, but does not execute Python.
- `copilot` decides when to call `run_code`.
- `code-executor` runs the Python, keeps session state alive, and stores artifacts temporarily on disk.

Current high-level flow:

```text
chat-ui
  -> copilot /ag-ui
  -> run_code tool
  -> code-executor POST /execute
  -> { stdout, images, plotly }
  -> copilot normalizes to structured artifacts
  -> chat-ui renders artifacts via its authenticated proxy route
```

The older marker-based `[IMAGE:...]` / `[CHART:...]` flow is no longer the current design.

## Session Model

Each chat thread gets its own Python worker process.

- session key: `session_id`, usually the LangGraph/CopilotKit thread id
- isolation model: one OS process per session
- persistence: variables and imports survive across multiple `/execute` calls for the same session
- idle cleanup: sessions older than `IDLE_TIMEOUT_SECONDS` are reaped by a background task
- hard cap: `MAX_SESSIONS`

### Rollback Behavior

On POSIX systems, every execution runs in a forked child of the current worker state:

- successful execution: the child becomes the new live worker, so state changes persist
- failed execution: the child exits and the previous good worker state remains
- timed-out execution: the child is terminated and the previous good worker state remains

That means a bad `run_code` call usually does not destroy the previous working session state.

## Execution Environment

The worker preloads a few common objects into `user_globals` before running `exec(...)`:

- `pd`: `pandas`
- `np`: `numpy`
- `plt`: `matplotlib.pyplot`
- `requests`: `requests`
- `pio`: `plotly.io`
- `save_image(image)`: saves a PIL image, bytes, or file-like object as a PNG artifact
- `wot`: helper client with:
  - `wot.read_property(...)`
  - `wot.write_property(...)`
  - `wot.invoke_action(...)`

The worker also registers `wot` as an importable module, so `import wot` works too.

Installed packages come from [`pyproject.toml`](./pyproject.toml) and currently include:

- `pandas`, `numpy`, `scipy`
- `matplotlib`, `plotly`, `seaborn`
- `requests`, `httpx`
- `openpyxl`, `tabulate`

## Artifact Handling

Artifacts are written into `ARTIFACTS_DIR`, which defaults to `/tmp/code-executor-artifacts`.

### Matplotlib

- `plt.show()` is overridden
- calling `plt.show()` saves the current figure as a PNG
- the PNG filename is returned in the `images` list

### Plotly

- `pio.show()` is overridden
- the default Plotly renderer is replaced with a capture renderer
- calling `fig.show()` writes the figure to a JSON file
- the JSON filename is returned in the `plotly` list
- `GET /artifacts/{filename}` converts Plotly JSON into standalone HTML for embedding in an `iframe`

### Cleanup

A background task runs every 60 seconds and:

- removes idle sessions
- deletes artifacts older than `ARTIFACTS_TTL_SECONDS`

Important current behavior:

- `DELETE /sessions/{session_id}` removes the live worker process
- it does not immediately delete artifact files for that session
- artifact files age out through the TTL cleanup pass

## API Surface

### `POST /execute`

Authenticated with `Authorization: Bearer <INTERNAL_API_KEY>`.

Request:

```json
{
  "session_id": "chat_123",
  "code": "print('hello')"
}
```

Response:

```json
{
  "stdout": "hello\n",
  "images": [],
  "plotly": []
}
```

### `GET /artifacts/{filename}`

Authenticated with `Authorization: Bearer <INTERNAL_API_KEY>`.

- `.png` files are returned directly
- `.json` Plotly files are converted to embeddable HTML

In normal app usage, the browser does not call this service directly. `chat-ui` proxies artifact access through its own `/api/artifacts/[id]` route.

### `DELETE /sessions/{session_id}`

Authenticated. Shuts down the worker process for that session.

Used by the thread delete flow in `chat-ui`.

### `GET /health`

Unauthenticated health endpoint returning a small payload including `active_sessions`.

## Security Model

This service is safer than running code inside the main agent process, but it is not a full sandbox or micro-VM.

Current protections:

- code runs in a separate process per session
- selected sensitive environment variables are removed before execution:
  - `INTERNAL_API_KEY`
  - `WOT_REGISTRY_TOKEN`
  - `OPENAI_API_KEY`
- production Docker runs the container as a non-root user
- the production Compose service uses:
  - read-only filesystem
  - `tmpfs` for `/tmp`
  - dropped Linux capabilities
  - `no-new-privileges`
  - CPU, memory, and PID limits
- `/execute`, `/artifacts/{filename}`, and `/sessions/{session_id}` require the internal API key

Important limits to keep in mind:

- user code still runs through normal Python `exec(...)`
- user code can import from the installed environment
- user code can make HTTP requests if container networking allows it
- there is no per-request container or VM reset

This service should stay on an internal network and should not be exposed directly to the public internet.

## Current Behavior That Matters For The UI

- `code-executor` returns raw `stdout`, `images`, and `plotly`
- `copilot` converts that to a smaller `stdout + artifacts` tool result
- `chat-ui` renders artifacts below the `run_code` tool call
- artifact placement is controlled by the UI/tool renderer, not by model-written markers

## Relevant Files

- [`code_executor/api/app.py`](./code_executor/api/app.py): FastAPI app and cleanup loop
- [`code_executor/api/routes.py`](./code_executor/api/routes.py): HTTP endpoints
- [`code_executor/api/dependencies.py`](./code_executor/api/dependencies.py): bearer-token auth
- [`code_executor/session_pool.py`](./code_executor/session_pool.py): worker lifecycle, `exec(...)`, output capture, rollback behavior
- [`code_executor/models/settings.py`](./code_executor/models/settings.py): environment-backed settings
- [`code_executor/models/schemas.py`](./code_executor/models/schemas.py): request/response models
- [`code_executor/utils.py`](./code_executor/utils.py): Plotly HTML wrapper
- [`Dockerfile`](./Dockerfile): container image

## Development

### With Docker Compose

```bash
docker compose up -d code-executor
```

The dev override:

- builds from [`Dockerfile`](./Dockerfile) `builder` stage
- mounts `./code-executor/code_executor -> /app/code_executor`
- runs Uvicorn with reload
- exposes port `8888` locally

### Directly

```bash
cd code-executor
pip install -e .
uvicorn code_executor.api:app --host 0.0.0.0 --port 8888 --reload
```

## Environment Variables

Defined in [`code_executor/models/settings.py`](./code_executor/models/settings.py):

- `IDLE_TIMEOUT_SECONDS`
- `EXECUTION_TIMEOUT_SECONDS`
- `MAX_SESSIONS`
- `LOG_LEVEL`
- `ARTIFACTS_DIR`
- `ARTIFACTS_TTL_SECONDS`
- `INTERNAL_API_KEY`
- `WOT_REGISTRY_URL`
- `WOT_REGISTRY_TOKEN`

## Current Gaps

- There is no dedicated automated test suite in this package today.
- Artifact cleanup is TTL-based rather than thread-scoped.
- The service favors practical isolation and rollback over strong sandbox guarantees.

## One-Sentence Summary

`code-executor` is a stateful, internal Python worker service: `copilot` sends code, the worker runs it with `exec(...)`, preserves per-thread state across calls, captures text and plots, and returns artifact filenames for the UI to render.
