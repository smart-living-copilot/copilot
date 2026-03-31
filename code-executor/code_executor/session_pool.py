"""Manages a pool of isolated Python processes, one per chat session."""

import asyncio
import io
import logging
import multiprocessing as mp
import os
import signal
import time
import traceback
import uuid
from contextlib import redirect_stdout
from dataclasses import dataclass, field

from code_executor.models import Settings

logger = logging.getLogger(__name__)

_RESULT_POLL_INTERVAL_SECONDS = 0.1
_SESSION_WATCHDOG_GRACE_SECONDS = 5
_MAX_STDOUT_CHARS = 2000


_SENSITIVE_ENV_VARS = [
    "INTERNAL_API_KEY",
    "WOT_REGISTRY_TOKEN",
    "OPENAI_API_KEY",
]


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_pid(pid: int) -> None:
    if pid <= 0:
        return

    for sig in (signal.SIGTERM, signal.SIGKILL):
        if not _pid_is_alive(pid):
            return
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return
        except PermissionError:
            return

        deadline = time.monotonic() + (0.5 if sig == signal.SIGTERM else 0)
        while time.monotonic() < deadline:
            if not _pid_is_alive(pid):
                return
            time.sleep(0.05)


def _worker_loop(
    conn: mp.connection.Connection,
    artifacts_dir: str,
    registry_url: str,
    registry_token: str,
    execution_timeout_seconds: int,
):
    """The entry point for the isolated background process."""
    # Remove sensitive env vars so user code cannot read them via os.environ
    for key in _SENSITIVE_ENV_VARS:
        os.environ.pop(key, None)

    # Set up Matplotlib backend before importing pyplot
    os.environ["MPLBACKEND"] = "Agg"
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import requests
    import plotly.io as pio
    from plotly.io._base_renderers import ExternalRenderer

    _captured_images = []
    _captured_plotly = []

    def _mock_show():
        filename = f"{uuid.uuid4()}.png"
        filepath = os.path.join(artifacts_dir, filename)
        plt.savefig(filepath, format="png", bbox_inches="tight", dpi=150)
        _captured_images.append(filename)
        plt.close("all")

    def _save_image(image):
        filename = f"{uuid.uuid4()}.png"
        filepath = os.path.join(artifacts_dir, filename)
        if hasattr(image, "save"):
            image.save(filepath, format="PNG")
        elif hasattr(image, "read"):
            with open(filepath, "wb") as f:
                f.write(image.read())
        elif isinstance(image, bytes):
            with open(filepath, "wb") as f:
                f.write(image)
        else:
            raise TypeError(
                f"save_image expects PIL Image, BytesIO, or bytes. Got {type(image)}"
            )
        _captured_images.append(filename)

    def _save_plotly_figure(fig):
        filename = f"{uuid.uuid4()}.json"
        filepath = os.path.join(artifacts_dir, filename)
        if hasattr(fig, "write_json"):
            fig.write_json(filepath)
            _captured_plotly.append(filename)

    def _mock_plotly_show(fig, *args, **kwargs):
        _save_plotly_figure(fig)

    class _CaptureRenderer(ExternalRenderer):
        def render(self, fig_dict):
            import plotly.graph_objects as go

            fig = go.Figure(fig_dict)
            _save_plotly_figure(fig)

    pio.renderers["capture"] = _CaptureRenderer()

    class _WotClient:
        """Synchronous client for direct WoT device interactions from the sandbox."""

        def __init__(self, base_url, token):
            self._base_url = base_url.rstrip("/")
            self._headers = {"Content-Type": "application/json"}
            if token:
                self._headers["Authorization"] = f"Bearer {token}"

        def _post(self, path, body):
            import requests as _req

            resp = _req.post(
                f"{self._base_url}{path}",
                json=body,
                headers=self._headers,
                timeout=120,
            )
            if not resp.ok:
                try:
                    detail = resp.json().get("detail", resp.text[:500])
                except Exception:
                    detail = resp.text[:500]
                raise RuntimeError(f"WoT request failed ({resp.status_code}): {detail}")
            return resp.json()

        def _extract_payload(self, result):
            """Extract the useful data from a runtime response envelope."""
            if not isinstance(result, dict):
                return result
            # read/write property responses
            r = result.get("result") or result.get("completed_result")
            if isinstance(r, dict):
                payload = r.get("payload", {})
                if payload.get("kind") == "inline":
                    return payload.get("data")
                return payload
            return result

        def read_property(self, thing_id, property_name, uri_variables=None):
            """Read a property value from a thing."""
            raw = self._post(
                "/api/wot/read-property",
                {
                    "thing_id": thing_id,
                    "property_name": property_name,
                    "uri_variables": uri_variables or {},
                },
            )
            return self._extract_payload(raw)

        def write_property(self, thing_id, property_name, value, uri_variables=None):
            """Write a property value to a thing."""
            raw = self._post(
                "/api/wot/write-property",
                {
                    "thing_id": thing_id,
                    "property_name": property_name,
                    "value": value,
                    "uri_variables": uri_variables or {},
                },
            )
            return self._extract_payload(raw)

        def invoke_action(self, thing_id, action_name, input=None, uri_variables=None):
            """Invoke an action on a thing."""
            input_payload = input
            if isinstance(input_payload, str):
                stripped = input_payload.lstrip()
                if stripped.startswith("{") or stripped.startswith("["):
                    import json as _json

                    try:
                        input_payload = _json.loads(input_payload)
                    except _json.JSONDecodeError:
                        pass

            raw = self._post(
                "/api/wot/invoke-action",
                {
                    "thing_id": thing_id,
                    "action_name": action_name,
                    "input": input_payload,
                    "uri_variables": uri_variables or {},
                },
            )
            return self._extract_payload(raw)

    _wot = _WotClient(registry_url, registry_token)

    # Register wot as an importable module so `import wot` works too
    import sys
    import types

    _wot_module = types.ModuleType("wot")
    _wot_module.read_property = _wot.read_property
    _wot_module.write_property = _wot.write_property
    _wot_module.invoke_action = _wot.invoke_action
    sys.modules["wot"] = _wot_module

    user_globals = {
        "__builtins__": __builtins__,
        "pd": pd,
        "np": np,
        "plt": plt,
        "requests": requests,
        "print": print,
        "pio": pio,
        "save_image": _save_image,
        "wot": _wot,
    }

    def _delete_artifacts(filenames: list[str]) -> None:
        for filename in filenames:
            filepath = os.path.join(artifacts_dir, filename)
            try:
                os.remove(filepath)
            except OSError:
                pass

    def _execute_code(code: str) -> dict:
        _captured_images.clear()
        _captured_plotly.clear()
        stdout_buffer = io.StringIO()

        original_plt_show = plt.show
        plt.show = _mock_show
        original_pio_show = pio.show
        original_renderer = pio.renderers.default
        pio.show = _mock_plotly_show
        pio.renderers.default = "capture"

        success = True
        try:
            with redirect_stdout(stdout_buffer):
                exec(code, user_globals)
        except Exception:
            success = False
            with redirect_stdout(stdout_buffer):
                tb = traceback.format_exc()
                # Keep only the error type/message and the offending line
                # to avoid overwhelming small models with long tracebacks.
                lines = tb.strip().splitlines()
                error_line = lines[-1] if lines else "Unknown error"
                # Find the last "File "<string>"" frame (user code, not library)
                source_line = ""
                for i, line in enumerate(lines):
                    if 'File "<string>"' in line:
                        # Next line is the offending source code
                        if i + 1 < len(lines):
                            source_line = lines[i + 1].strip()
                if source_line:
                    print(f"Error: {error_line}\nAt: {source_line}")
                else:
                    print(f"Error: {error_line}")
        finally:
            plt.show = original_plt_show
            pio.show = original_pio_show
            pio.renderers.default = original_renderer

        images = _captured_images.copy()
        plotly = _captured_plotly.copy()
        if not success:
            _delete_artifacts(images + plotly)
            images = []
            plotly = []

        stdout = stdout_buffer.getvalue()
        if len(stdout) > _MAX_STDOUT_CHARS:
            stdout = (
                stdout[:_MAX_STDOUT_CHARS]
                + f"\n\n... truncated ({len(stdout)} chars total)."
                " Print only summaries, not raw data."
            )

        return {
            "ok": success,
            "stdout": stdout,
            "images": images,
            "plotly": plotly,
        }

    # Main execution loop
    while True:
        try:
            # Wait for code to execute
            code = conn.recv()
            if code is None:
                break  # Shutdown signal

            if not hasattr(os, "fork"):
                result = _execute_code(code)
                conn.send(
                    {
                        "stdout": result["stdout"],
                        "images": result["images"],
                        "plotly": result["plotly"],
                    }
                )
                continue

            # Fork the current session so failed or timed-out runs can roll back
            # to the last good globals, while successful runs become the new state.
            result_reader, result_writer = mp.Pipe(duplex=False)
            child_pid = os.fork()

            if child_pid == 0:
                result_reader.close()
                result = {
                    "ok": False,
                    "stdout": "",
                    "images": [],
                    "plotly": [],
                }
                try:
                    result = _execute_code(code)
                    result_writer.send(result)
                except BaseException:
                    result = {
                        "ok": False,
                        "stdout": traceback.format_exc(),
                        "images": [],
                        "plotly": [],
                    }
                    try:
                        result_writer.send(result)
                    except Exception:
                        pass
                finally:
                    result_writer.close()

                if result.get("ok"):
                    # Keep the mutated globals by letting the child continue as
                    # the live session worker after the parent returns the result.
                    continue
                os._exit(0)

            result_writer.close()
            deadline = time.monotonic() + execution_timeout_seconds
            response = None
            promoted_child = False

            while time.monotonic() < deadline:
                remaining = max(0.0, deadline - time.monotonic())
                poll_timeout = min(_RESULT_POLL_INTERVAL_SECONDS, remaining)

                if result_reader.poll(poll_timeout):
                    try:
                        child_result = result_reader.recv()
                    except EOFError:
                        response = {
                            "error": "Code execution worker exited without returning a result.",
                            "stdout": "",
                            "images": [],
                            "plotly": [],
                        }
                    else:
                        if child_result.get("ok"):
                            response = {
                                "stdout": child_result["stdout"],
                                "images": child_result["images"],
                                "plotly": child_result["plotly"],
                                "worker_pid": child_pid,
                            }
                            promoted_child = True
                        else:
                            response = {
                                "stdout": child_result.get("stdout", ""),
                                "images": [],
                                "plotly": [],
                            }
                            try:
                                os.waitpid(child_pid, 0)
                            except ChildProcessError:
                                pass
                    break

                finished_pid, _ = os.waitpid(child_pid, os.WNOHANG)
                if finished_pid == child_pid:
                    if result_reader.poll(0):
                        try:
                            child_result = result_reader.recv()
                        except EOFError:
                            child_result = None
                        if child_result and not child_result.get("ok"):
                            response = {
                                "stdout": child_result.get("stdout", ""),
                                "images": [],
                                "plotly": [],
                            }
                            break
                    response = {
                        "error": "Code execution worker exited unexpectedly.",
                        "stdout": "",
                        "images": [],
                        "plotly": [],
                    }
                    break

            if response is None:
                _terminate_pid(child_pid)
                try:
                    os.waitpid(child_pid, 0)
                except ChildProcessError:
                    pass
                response = {
                    "error": (
                        f"Code execution timed out after {execution_timeout_seconds} seconds."
                    ),
                    "stdout": "",
                    "images": [],
                    "plotly": [],
                }

            result_reader.close()
            conn.send(response)
            if promoted_child:
                return

        except EOFError:
            break
        except Exception as e:
            conn.send({"error": str(e), "stdout": "", "images": [], "plotly": []})


@dataclass
class _SessionEntry:
    worker_pid: int
    parent_conn: mp.connection.Connection
    last_used: float = field(default_factory=time.time)


class SessionPool:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sessions: dict[str, _SessionEntry] = {}
        self._lock = asyncio.Lock()
        self._artifacts_dir = settings.artifacts_dir
        os.makedirs(self._artifacts_dir, exist_ok=True)

    def _get_or_create_session(self, session_id: str) -> _SessionEntry:
        if session_id in self._sessions:
            entry = self._sessions[session_id]
            if not _pid_is_alive(entry.worker_pid):
                logger.warning(
                    "Worker process for session %s is dead, recreating", session_id
                )
                try:
                    entry.parent_conn.close()
                except Exception:
                    pass
                del self._sessions[session_id]
            else:
                entry.last_used = time.time()
                return entry

        if len(self._sessions) >= self._settings.max_sessions:
            raise RuntimeError(
                f"Maximum number of sessions ({self._settings.max_sessions}) reached"
            )

        logger.info("Creating isolated process session for %s", session_id)

        parent_conn, child_conn = mp.Pipe()
        process = mp.Process(
            target=_worker_loop,
            args=(
                child_conn,
                self._artifacts_dir,
                self._settings.wot_registry_url,
                self._settings.wot_registry_token,
                self._settings.execution_timeout_seconds,
            ),
            daemon=True,
        )
        process.start()
        child_conn.close()

        entry = _SessionEntry(worker_pid=process.pid or -1, parent_conn=parent_conn)
        self._sessions[session_id] = entry
        return entry

    async def execute(self, session_id: str, code: str) -> dict:
        """Execute code in the isolated session process, return {stdout, images, plotly}."""
        async with self._lock:
            entry = self._get_or_create_session(session_id)

        entry.last_used = time.time()
        timeout = self._settings.execution_timeout_seconds
        watchdog_timeout = timeout + _SESSION_WATCHDOG_GRACE_SECONDS

        # Run the blocking pipe communication in a thread
        loop = asyncio.get_event_loop()

        def _communicate():
            entry.parent_conn.send(code)
            if not entry.parent_conn.poll(watchdog_timeout):
                raise TimeoutError(
                    "Code execution session became unresponsive while waiting for a result"
                )
            return entry.parent_conn.recv()

        try:
            result = await loop.run_in_executor(None, _communicate)
        except TimeoutError:
            await self.shutdown(session_id)
            raise RuntimeError(
                f"Code execution session became unresponsive after {watchdog_timeout} seconds."
            )
        except (BrokenPipeError, EOFError, OSError):
            # Worker process died — clean up and recreate on next call
            await self.shutdown(session_id)
            raise RuntimeError("Code execution session crashed. Please try again.")

        next_worker_pid = result.pop("worker_pid", None)
        if next_worker_pid:
            entry.worker_pid = next_worker_pid

        if "error" in result:
            raise RuntimeError(result["error"])

        return result

    async def shutdown(self, session_id: str) -> None:
        async with self._lock:
            entry = self._sessions.pop(session_id, None)
            if entry:
                logger.info("Removed session %s", session_id)
                try:
                    entry.parent_conn.send(None)
                except Exception:
                    pass
                finally:
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        if not _pid_is_alive(entry.worker_pid):
                            break
                        time.sleep(0.05)
                    _terminate_pid(entry.worker_pid)
                    try:
                        entry.parent_conn.close()
                    except Exception:
                        pass

    async def cleanup_idle(self) -> None:
        now = time.time()
        async with self._lock:
            to_remove = [
                sid
                for sid, entry in self._sessions.items()
                if now - entry.last_used > self._settings.idle_timeout_seconds
            ]
        for sid in to_remove:
            logger.info("Reaping idle session %s", sid)
            await self.shutdown(sid)

    def cleanup_old_artifacts(self) -> None:
        now = time.time()
        ttl = self._settings.artifacts_ttl_seconds
        try:
            for f in os.listdir(self._artifacts_dir):
                filepath = os.path.join(self._artifacts_dir, f)
                if os.path.isfile(filepath):
                    age = now - os.path.getmtime(filepath)
                    if age > ttl:
                        os.remove(filepath)
        except OSError:
            pass

    async def shutdown_all(self) -> None:
        async with self._lock:
            session_ids = list(self._sessions.keys())
        for sid in session_ids:
            await self.shutdown(sid)

    @property
    def active_count(self) -> int:
        return len(self._sessions)
