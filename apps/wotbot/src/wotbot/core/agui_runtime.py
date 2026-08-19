"""AG-UI runtime helpers for WoTBot."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ag_ui.core.events import RunErrorEvent
from ag_ui.core.types import RunAgentInput
from ag_ui.encoder import EventEncoder
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage

from wotbot.threads import suggest_thread_title, sync_thread_after_run

logger = logging.getLogger(__name__)

EMBED_EPHEMERAL_THREAD_PREFIX = "embed-ephemeral-"
_UNSET = object()

# Shown in place of the response when a run is cancelled or fails before
# producing one. See AguiRuntime._finalize_interrupted_run for why this needs
# to exist at all.
_INTERRUPTED_TURN_NOTICE = "The response was interrupted before it finished. Try asking again."


class _AGUIAgentProxy:
    name = "wotbot"

    def __init__(self, runtime: AguiRuntime):
        self._runtime = runtime

    def clone(self):
        return _AGUIAgentProxy(self._runtime)

    async def run(self, input_data):
        async for event in self._runtime.run(input_data):
            yield event


class AguiRuntime:
    """Holds AG-UI request state and lifecycle behavior for the process."""

    def __init__(self) -> None:
        self.agent: Any | None = None
        self.checkpointer: Any | None = None
        self.settings: Any | None = None
        # The compiled graph itself (as opposed to ``agent``, the AG-UI
        # wrapper around it) -- needed to read/patch checkpoint state
        # directly in _finalize_interrupted_run, independent of whatever the
        # AG-UI adapter's own request/response cycle is doing.
        self.graph: Any | None = None
        self._thread_run_locks: dict[str, asyncio.Lock] = {}
        self._thread_run_locks_guard = asyncio.Lock()

    def configure(
        self,
        *,
        agent: Any | None | object = _UNSET,
        checkpointer: Any | None | object = _UNSET,
        settings: Any | None | object = _UNSET,
        graph: Any | None | object = _UNSET,
    ) -> None:
        if agent is not _UNSET:
            self.agent = agent
        if checkpointer is not _UNSET:
            self.checkpointer = checkpointer
        if settings is not _UNSET:
            self.settings = settings
        if graph is not _UNSET:
            self.graph = graph

    def clear_request_state(self) -> None:
        self.agent = None
        self.checkpointer = None
        self.graph = None
        self._thread_run_locks = {}

    def current_settings(self) -> Any | None:
        return self.settings

    def current_checkpointer(self) -> Any | None:
        return self.checkpointer

    def create_agent_proxy(self) -> _AGUIAgentProxy:
        return _AGUIAgentProxy(self)

    async def run(self, input_data):
        if self.agent is None:
            raise RuntimeError("AG-UI agent is not ready")

        input_data = _with_forwarded_reasoning_effort(input_data)
        thread_id = _request_thread_id(input_data)
        run_id = _request_run_id(input_data)
        heartbeat_timeout = _heartbeat_timeout(self.settings)
        uses_thread_lock = bool(thread_id)
        started = time.perf_counter()
        completed = False
        logger.info(
            "AG-UI run started thread_id=%s run_id=%s uses_thread_lock=%s heartbeat_timeout=%s",
            thread_id,
            run_id,
            uses_thread_lock,
            heartbeat_timeout,
        )
        try:
            if thread_id:
                # Proactively heal before starting, not just reactively after
                # failing (finally, below): the reactive finalize for a PRIOR
                # run on this thread runs in a background task specifically
                # so a cancellation doesn't kill it (see
                # run_persistence_operation) -- which means it isn't
                # guaranteed to have finished by the time a fast reconnect
                # (e.g. the user hits refresh right after clicking stop)
                # starts a new run here. Checking again at the top closes
                # that race: whichever of the two actually gets the thread
                # lock first does the healing, the other finds nothing left
                # to do.
                await self._finalize_interrupted_run(thread_id)
                lock = await self._thread_run_lock(thread_id)
                async with lock:
                    async for event in self.agent.run(input_data):
                        yield event
            else:
                async for event in self.agent.run(input_data):
                    yield event
            completed = True
        except (asyncio.CancelledError, GeneratorExit):
            logger.warning(
                "AG-UI run cancelled/closed thread_id=%s run_id=%s elapsed_ms=%.1f",
                thread_id,
                run_id,
                _elapsed_ms(started),
            )
            raise
        except Exception:
            logger.exception(
                "AG-UI run failed thread_id=%s run_id=%s elapsed_ms=%.1f",
                thread_id,
                run_id,
                _elapsed_ms(started),
            )
            raise
        finally:
            await self.finalize_thread_run(thread_id, completed=completed)
        if completed:
            logger.info(
                "AG-UI run finished thread_id=%s run_id=%s elapsed_ms=%.1f",
                thread_id,
                run_id,
                _elapsed_ms(started),
            )

    async def finalize_thread_run(self, thread_id: str | None, *, completed: bool = True) -> None:
        if _is_embed_ephemeral_thread(thread_id):
            if thread_id:
                cancelled = await self.delete_checkpoint_thread(thread_id)
                if cancelled:
                    raise asyncio.CancelledError
            return

        cancelled = False
        if not completed:
            # A run that didn't complete -- cancelled (stop button, closed
            # tab, dropped connection) or a genuine error -- can leave the
            # checkpoint's last message as an unanswered HumanMessage: the
            # graph never reached a node that appended a response. Left as
            # is, every future reconnect to this thread finds that same
            # unfinished turn and reattempts it, failing again immediately.
            # Closing the turn out here means a reconnect just replays
            # ordinary finished history instead of unfinished work to redo.
            cancelled = await self.run_persistence_operation(
                self._finalize_interrupted_run(thread_id),
                error_message=f"Failed to finalize interrupted run for {thread_id}",
            )

        metadata_cancelled = await self.run_persistence_operation(
            self._sync_thread_metadata_after_run(thread_id),
            error_message=f"Failed to sync thread metadata for {thread_id}",
        )
        cancelled = cancelled or metadata_cancelled

        if cancelled:
            raise asyncio.CancelledError

    async def _finalize_interrupted_run(self, thread_id: str | None) -> None:
        """Idempotent: called both proactively (top of run(), before this
        run touches anything) and reactively (finally, below, after this run
        fails to complete). Either caller can win the race to run first --
        whichever does, the other finds the checkpoint already clean and
        no-ops via the isinstance check below.
        """
        if not thread_id or self.graph is None:
            return

        # Share the per-thread run lock with normal runs: if a new run for
        # this thread starts before this gets to run, wait for it rather
        # than racing it. By the time the lock is free the checkpoint's last
        # message is very likely a real response already, in which case the
        # isinstance check below is a no-op -- this never overwrites fresh
        # content with a stale "interrupted" notice.
        lock = await self._thread_run_lock(thread_id)
        async with lock:
            config = {"configurable": {"thread_id": thread_id}}
            state = await self.graph.aget_state(config)
            messages = state.values.get("messages", []) if state and state.values else []
            if not messages or not isinstance(messages[-1], HumanMessage):
                return
            await self.graph.aupdate_state(
                config,
                {"messages": [AIMessage(content=_INTERRUPTED_TURN_NOTICE)]},
            )

    async def run_persistence_operation(
        self,
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

    async def delete_checkpoint_thread(self, thread_id: str) -> bool:
        if self.checkpointer is None:
            return False

        return await self.run_persistence_operation(
            self.checkpointer.adelete_thread(thread_id),
            error_message=f"Failed to delete checkpoints for {thread_id}",
        )

    async def _thread_run_lock(self, thread_id: str) -> asyncio.Lock:
        async with self._thread_run_locks_guard:
            lock = self._thread_run_locks.get(thread_id)
            if lock is None:
                lock = asyncio.Lock()
                self._thread_run_locks[thread_id] = lock
            return lock

    async def _get_checkpoint_tuple(self, thread_id: str) -> Any | None:
        if self.checkpointer is None:
            return None

        return await self.checkpointer.aget_tuple({"configurable": {"thread_id": thread_id}})

    async def _sync_thread_metadata_after_run(self, thread_id: str | None) -> None:
        if not thread_id or self.settings is None:
            return

        title = await self._suggest_thread_title(thread_id)
        await asyncio.to_thread(
            sync_thread_after_run,
            thread_id,
            suggested_title=title,
        )

    async def _suggest_thread_title(self, thread_id: str) -> str | None:
        state = await self._get_checkpoint_tuple(thread_id)
        if state is None or state.checkpoint is None:
            return None

        channel_values = state.checkpoint.get("channel_values", {})
        messages = channel_values.get("messages", [])
        if not isinstance(messages, list):
            return None

        return suggest_thread_title(messages)

    async def sse_with_heartbeat(self, events, encoder, timeout):
        """Encode AG-UI events as SSE, emitting keepalive comments during silence.

        A slow tool call (e.g. a long matplotlib render in the code executor)
        produces no events for a stretch; without a heartbeat the consuming undici
        client aborts the response body with ``UND_ERR_BODY_TIMEOUT`` before the
        final answer arrives. ``timeout=None`` disables the heartbeat.

        The stream's termination cause is logged with the bytes/events sent so an
        abrupt close can be told apart (normal end vs. cancellation vs. a raised
        exception). On a genuine exception we emit a terminal ``RUN_ERROR`` event so
        the client gets a clean error instead of a dropped socket.
        """
        ait = events.__aiter__()
        pending: asyncio.Task | None = None
        sent_events = 0
        sent_bytes = 0

        def _emit(chunk: str) -> str:
            nonlocal sent_bytes
            sent_bytes += len(chunk.encode("utf-8"))
            return chunk

        try:
            while True:
                if pending is None:
                    pending = asyncio.ensure_future(ait.__anext__())
                try:
                    event = await asyncio.wait_for(asyncio.shield(pending), timeout)
                except asyncio.TimeoutError:
                    yield _emit(": keepalive\n\n")
                    continue
                except StopAsyncIteration:
                    pending = None
                    logger.info(
                        "AG-UI stream completed: %d events, %d bytes",
                        sent_events,
                        sent_bytes,
                    )
                    break
                pending = None
                sent_events += 1
                yield _emit(encoder.encode(event))
        except (asyncio.CancelledError, GeneratorExit):
            logger.warning(
                "AG-UI stream cancelled/closed after %d events, %d bytes",
                sent_events,
                sent_bytes,
            )
            raise
        except Exception as exc:
            logger.exception(
                "AG-UI stream raised after %d events, %d bytes: %s",
                sent_events,
                sent_bytes,
                exc,
            )
            try:
                yield _emit(encoder.encode(RunErrorEvent(message=f"{type(exc).__name__}: {exc}")))
            except Exception:  # pragma: no cover - stream already gone
                pass
        finally:
            if pending is not None and not pending.done():
                pending.cancel()
            aclose = getattr(ait, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:  # pragma: no cover - best-effort cleanup
                    pass

    def register_endpoint(self, app: FastAPI, path: str = "/ag-ui") -> None:
        """Register the AG-UI SSE endpoint with a keepalive heartbeat."""

        @app.get(f"{path}/health")
        async def langgraph_agent_health():
            return {
                "status": "ok",
                "agent": {
                    "name": _AGUIAgentProxy.name,
                },
            }

        @app.post(path)
        async def langgraph_agent_endpoint(input_data: RunAgentInput, request: Request):
            encoder = EventEncoder(accept=request.headers.get("accept"))
            request_agent = self.create_agent_proxy()
            timeout = _heartbeat_timeout(self.settings)
            return StreamingResponse(
                self.sse_with_heartbeat(request_agent.run(input_data), encoder, timeout),
                media_type=encoder.get_content_type(),
            )


def _is_embed_ephemeral_thread(thread_id: str | None) -> bool:
    return isinstance(thread_id, str) and thread_id.startswith(EMBED_EPHEMERAL_THREAD_PREFIX)


def _request_thread_id(input_data: Any) -> str | None:
    return _request_string(input_data, ("threadId", "thread_id"))


def _request_run_id(input_data: Any) -> str | None:
    return _request_string(input_data, ("runId", "run_id"))


def _with_forwarded_reasoning_effort(input_data: Any) -> Any:
    """Make the request-scoped selector value win over stale client state.

    CopilotKit sends the graph's last state snapshot back on every run. The
    AG-UI LangGraph adapter merges ``forwardedProps`` first and that state
    second, so a previously checkpointed ``reasoning_effort`` otherwise masks
    a newly selected value. Mirror the forwarded value into this request's
    state before handing it to the adapter; normal node-level allow-list
    validation still decides whether the value is honored.
    """
    if isinstance(input_data, dict):
        forwarded_props = input_data.get("forwardedProps") or input_data.get(
            "forwarded_props"
        )
        state = input_data.get("state")
    else:
        forwarded_props = getattr(input_data, "forwarded_props", None)
        state = getattr(input_data, "state", None)

    if not isinstance(forwarded_props, dict):
        return input_data

    effort = forwarded_props.get("reasoningEffort")
    if effort is None:
        effort = forwarded_props.get("reasoning_effort")
    if not isinstance(effort, str) or (state is not None and not isinstance(state, dict)):
        return input_data

    updated_state = {**(state or {}), "reasoning_effort": effort}
    if isinstance(input_data, dict):
        return {**input_data, "state": updated_state}

    model_copy = getattr(input_data, "model_copy", None)
    return model_copy(update={"state": updated_state}) if model_copy else input_data


def _request_string(input_data: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(input_data, dict):
        return _string_from_mapping(input_data, keys)

    direct_value = _string_from_attrs(input_data, keys)
    if direct_value:
        return direct_value
    configurable = getattr(input_data, "configurable", None)
    return _string_from_mapping(configurable, keys) if isinstance(configurable, dict) else None


def _string_from_mapping(value: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    direct_value = _first_string_value(value, keys)
    if direct_value:
        return direct_value
    configurable = value.get("configurable")
    return _first_string_value(configurable, keys)


def _string_from_attrs(value: Any, keys: tuple[str, ...]) -> str | None:
    for attr in keys:
        raw_value = getattr(value, attr, None)
        if isinstance(raw_value, str) and raw_value:
            return raw_value
    return None


def _first_string_value(value: Any, keys: tuple[str, ...]) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in keys:
        raw_value = value.get(key)
        if isinstance(raw_value, str) and raw_value:
            return raw_value
    return None


def _heartbeat_timeout(settings: Any | None) -> float | None:
    interval = settings.sse_heartbeat_seconds if settings else 15.0
    return interval if interval and interval > 0 else None


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


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
