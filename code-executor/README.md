# Code Executor

`code-executor` is the internal Python execution service used by Smart Living Copilot's `run_code` tool. It accepts Python snippets over HTTP, executes them inside a long-lived worker process for a specific chat session, and returns text output plus any generated visual artifacts.

## What It Does

- Runs Python code sent by the Copilot service.
- Keeps variables and imports alive for the lifetime of a chat session.
- Captures `print()` output.
- Turns `matplotlib` and `plotly` visualizations into artifacts the UI can render inline.
- Exposes a small set of WoT/data helpers inside every execution session.

## End-to-End Flow

1. The Copilot app calls `run_code(...)` in [`../copilot/copilot/tools/run_code.py`](../copilot/copilot/tools/run_code.py).
2. `run_code` sends `POST /execute` to the Code Executor with:
   - `session_id`: the current `chat_id`
   - `code`: the Python snippet to run
3. FastAPI authenticates the request with `INTERNAL_API_KEY` and forwards it to `SessionPool`.
4. `SessionPool` reuses or creates one worker process for that `session_id`.
5. The worker executes the code with `exec(code, user_globals)`.
6. `stdout`, image filenames, and Plotly filenames are returned as JSON.
7. The Copilot tool rewrites the response into compact markers like `[IMAGE:...png]` and `[CHART:...json]`.
8. The chat UI parses those markers and loads the files through its artifact proxy route.

## Session Model

Each chat gets its own Python worker process.

- Session key: `session_id` from the request, usually the chat id
- Isolation model: one OS process per session
- Persistence: globals survive across multiple `/execute` calls for the same session
- Failure handling: each execution runs against a forked snapshot of the current session on POSIX systems; successful runs become the new session state, while exceptions and timeouts keep the last good state
- Default max sessions: `50`
- Default idle timeout: `1800` seconds
- Default execution timeout: `300` seconds

Important consequence: if one code cell defines `df = ...`, the next code cell in the same chat can reuse `df` without recreating it.

Another important consequence: if a later `run_code` call fails or times out, the previous successful session state remains usable instead of being discarded.

## Execution Environment

The worker process preloads a few common objects into `user_globals` before running user code:

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

The worker also registers `wot` as an importable module, so `import wot` works, although the prompts usually tell the model to use the preloaded object directly.

Installed packages come from [`pyproject.toml`](./pyproject.toml) and include:

- `pandas`, `numpy`, `scipy`
- `matplotlib`, `plotly`, `seaborn`
- `requests`, `httpx`
- `openpyxl`, `tabulate`

## Artifact Handling

Artifacts are written into `ARTIFACTS_DIR`, which defaults to `/tmp/code-executor-artifacts`.

### Matplotlib

- The worker overrides `plt.show()`.
- Calling `plt.show()` saves the current figure as a PNG.
- The PNG filename is returned in the `images` list.

### Plotly

- The worker overrides `pio.show()` and sets the default renderer to a custom capture renderer.
- Calling `fig.show()` writes the figure to a JSON file.
- The JSON filename is returned in the `plotly` list.
- `GET /artifacts/{filename}` converts Plotly JSON into standalone HTML for embedding in an `iframe`.

### Cleanup

A background task runs every 60 seconds and:

- removes idle sessions
- deletes old artifacts past `ARTIFACTS_TTL_SECONDS` (default: `3600`)

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

### `DELETE /sessions/{session_id}`

Authenticated. Shuts down the worker process for that session.

The chat UI calls this when a chat is deleted in [`../chat-ui/src/app/api/chats/[chatId]/route.ts`](../chat-ui/src/app/api/chats/[chatId]/route.ts).

### `GET /artifacts/{filename}`

Authenticated. Serves saved artifacts by filename.

- `.png` files are returned directly
- `.json` Plotly files are converted to embeddable HTML

### `GET /health`

Returns a simple status payload with the current active session count.

## Security Model

This service is safer than running code in the main Copilot process, but it is not a full VM-style sandbox.

Current protections:

- code runs in a separate process per session
- selected sensitive env vars are removed before execution:
  - `INTERNAL_API_KEY`
  - `WOT_REGISTRY_TOKEN`
  - `OPENAI_API_KEY`
  - `LANGFUSE_PUBLIC_KEY`
  - `LANGFUSE_SECRET_KEY`
- `matplotlib` uses the non-GUI `Agg` backend
- production Docker config runs the container as:
  - non-root user
  - read-only filesystem
  - `/tmp` backed by `tmpfs`
  - dropped Linux capabilities
  - `no-new-privileges`
  - CPU, memory, and PID limits

Important limits to keep in mind:

- code still runs with normal Python `exec()`
- code can import from the installed environment
- code can make HTTP requests if the container network allows it
- there is no per-request container or micro-VM

## Relevant Files

- [`code_executor/api/app.py`](./code_executor/api/app.py): FastAPI app and background cleanup loop
- [`code_executor/api/routes.py`](./code_executor/api/routes.py): HTTP endpoints
- [`code_executor/api/dependencies.py`](./code_executor/api/dependencies.py): bearer-token auth
- [`code_executor/session_pool.py`](./code_executor/session_pool.py): worker lifecycle, `exec()`, output capture, timeouts
- [`code_executor/models/settings.py`](./code_executor/models/settings.py): environment-backed settings
- [`code_executor/utils.py`](./code_executor/utils.py): Plotly HTML wrapper
- [`Dockerfile`](./Dockerfile): container image entrypoint

## Running It

### With Docker Compose

The main stack defines the service in [`../docker-compose.yaml`](../docker-compose.yaml), and the dev override enables hot reload in [`../docker-compose.override.yaml`](../docker-compose.override.yaml).

Typical dev usage:

```bash
docker compose up code-executor
```

### Directly

From the `code-executor` directory:

```bash
pip install -e .
uvicorn code_executor.api:app --host 0.0.0.0 --port 8888 --reload
```

Useful environment variables:

- `INTERNAL_API_KEY`
- `IDLE_TIMEOUT_SECONDS`
- `EXECUTION_TIMEOUT_SECONDS`
- `MAX_SESSIONS`
- `ARTIFACTS_DIR`
- `ARTIFACTS_TTL_SECONDS`
- `WOT_REGISTRY_URL`
- `WOT_REGISTRY_TOKEN`
- `LOG_LEVEL`

## One-Sentence Summary

`code-executor` is a stateful, per-chat Python worker service: Copilot sends code, the worker runs it with `exec()`, captures text and charts, and the UI renders the returned artifacts inline.
