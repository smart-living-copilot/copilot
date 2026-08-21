"""LangGraph run streaming for the ``useStream`` chat transport.

The wire format is dictated by ``FetchStreamTransport``/``useStream`` in
``@langchain/langgraph-sdk``. Each LangGraph stream part becomes one SSE frame:

* the stream mode becomes the SSE ``event`` name
* a subgraph namespace is appended to that name, ``|``-separated
* the payload is JSON in the ``data`` field

The client parses this as ``expected === actual || actual.startsWith(expected + "|")``
and recovers the namespace with ``event.split("|").slice(1)``. LangGraph's Python
``StreamMode`` literals already match the event names the client handles, so no
mode translation is needed.

Note ``messages`` mode: the client destructures ``const [serialized, metadata] = data``,
so that payload must serialize as a 2-element array, never a bare message.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import Any

from fastapi.encoders import jsonable_encoder
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.types import Command

from wotbot.core.sse import format_sse_error, format_sse_event
from wotbot.threads import suggest_thread_title, sync_thread_after_run

logger = logging.getLogger(__name__)

# "custom" is included so graph nodes can push progress via get_stream_writer()
# without another transport. "checkpoints"/"tasks"/"debug" are deliberately left
# out: the client has callbacks for them but nothing here consumes them, and
# they dominate payload size on graphs with large state.
RUN_STREAM_MODES: tuple[str, ...] = ("values", "messages", "updates", "custom")
_INTERRUPTED_TURN_NOTICE = "The response was interrupted before it finished. Try asking again."
_CONCURRENT_RUN_NOTICE = "A response is already running for this thread."


def _event_name(mode: str, namespace: Sequence[str] | None) -> str:
    if not namespace:
        return mode
    return "|".join((mode, *namespace))


def _serialize(mode: str, payload: Any) -> Any:
    """Convert one stream payload to JSON-safe data.

    ``jsonable_encoder`` turns the ``messages`` mode tuple into the 2-element
    array the client requires, and renders message objects with the ``type``
    discriminator it switches on. Chunk types arrive as ``"AIMessageChunk"``;
    the client normalizes those itself (``type.slice(0, -12).toLowerCase()``),
    so they are passed through untouched.
    """
    return jsonable_encoder(payload)


def _build_command(raw: Any) -> Command | None:
    if not isinstance(raw, dict):
        return None
    kwargs: dict[str, Any] = {}
    for key in ("resume", "goto", "update"):
        if raw.get(key) is not None:
            kwargs[key] = raw[key]
    return Command(**kwargs) if kwargs else None


@dataclass(slots=True)
class _ThreadLockEntry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


class RunRegistry:
    """Tracks the in-flight run per thread so a cancel request can stop it."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._thread_locks: dict[str, _ThreadLockEntry] = {}

    def register(self, thread_id: str, task: asyncio.Task[None]) -> bool:
        existing = self._tasks.get(thread_id)
        if existing is not None and not existing.done():
            return False
        self._tasks[thread_id] = task
        return True

    def unregister(self, thread_id: str, task: asyncio.Task[None]) -> None:
        if self._tasks.get(thread_id) is task:
            del self._tasks[thread_id]

    def cancel(self, thread_id: str) -> bool:
        task = self._tasks.get(thread_id)
        if task is None or task.done():
            return False
        task.cancel()
        logger.info("Cancelled in-flight run thread_id=%s", thread_id)
        return True

    @asynccontextmanager
    async def thread_lock(self, thread_id: str) -> AsyncIterator[None]:
        entry = self._thread_locks.get(thread_id)
        if entry is None:
            entry = _ThreadLockEntry()
            self._thread_locks[thread_id] = entry
        entry.users += 1
        try:
            async with entry.lock:
                yield
        finally:
            entry.users -= 1
            if entry.users == 0 and self._thread_locks.get(thread_id) is entry:
                del self._thread_locks[thread_id]


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") in {"text", "output_text"}:
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


class _PartialAssistantText:
    """Keep only the assistant message currently streaming when a run stops."""

    def __init__(self) -> None:
        self._message_id: str | None = None
        self._parts: list[str] = []

    def observe(self, mode: str, payload: Any) -> None:
        if mode != "messages" or not isinstance(payload, (list, tuple)) or not payload:
            return

        message = payload[0]
        if not isinstance(message, AIMessageChunk):
            return

        message_id = message.id if isinstance(message.id, str) else None
        if message_id and message_id != self._message_id:
            self._message_id = message_id
            self._parts.clear()

        text = _message_text(message.content)
        if text:
            self._parts.append(text)

        if message.chunk_position == "last":
            self._message_id = None
            self._parts.clear()

    def text(self) -> str:
        return "".join(self._parts).strip()


async def _finalize_interrupted_run(
    graph: Any,
    thread_id: str,
    *,
    partial_text: str = "",
) -> None:
    """Close a checkpoint whose last user turn never received an answer."""
    config = {"configurable": {"thread_id": thread_id}}
    state = await graph.aget_state(config)
    messages = state.values.get("messages", []) if state and state.values else []
    if not messages or not isinstance(messages[-1], HumanMessage):
        return

    await graph.aupdate_state(
        config,
        {"messages": [AIMessage(content=partial_text.strip() or _INTERRUPTED_TURN_NOTICE)]},
    )


async def _sync_thread_metadata(
    graph: Any,
    thread_id: str,
    sync_thread: Callable[..., Any],
) -> None:
    config = {"configurable": {"thread_id": thread_id}}
    state = await graph.aget_state(config)
    messages = state.values.get("messages", []) if state and state.values else []
    title = suggest_thread_title(messages) if isinstance(messages, list) else None
    await asyncio.to_thread(sync_thread, thread_id, suggested_title=title)


def _log_background_exception(task: asyncio.Task[None], message: str) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        logger.warning("%s: task was cancelled", message)
    except Exception as exc:
        logger.error("%s: %s", message, exc, exc_info=exc)


async def _persist(operation: Any, *, error_message: str) -> None:
    """Shield checkpoint repair and metadata updates from request cancellation."""
    task = asyncio.create_task(operation)
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        task.add_done_callback(lambda done: _log_background_exception(done, error_message))
    except Exception:
        logger.exception(error_message)


async def _finish_run(
    *,
    graph: Any,
    registry: RunRegistry,
    thread_id: str,
    completed: bool,
    partial_text: str,
    sync_thread: Callable[..., Any],
) -> None:
    # Re-acquire the same lock used by graph execution. If a reconnect wins the
    # race, its proactive repair handles the dangling turn and this becomes a
    # harmless no-op after that run finishes.
    async with registry.thread_lock(thread_id):
        if not completed:
            await _finalize_interrupted_run(
                graph,
                thread_id,
                partial_text=partial_text,
            )
        await _sync_thread_metadata(graph, thread_id, sync_thread)


async def stream_run(
    *,
    graph: Any,
    registry: RunRegistry,
    thread_id: str,
    input_data: Any,
    context: dict[str, Any] | None,
    command: Any,
    sync_thread: Callable[..., Any] = sync_thread_after_run,
) -> AsyncIterator[str]:
    """Yield SSE frames for one graph run, cancellable via ``registry``.

    The graph is consumed by a background task feeding a queue rather than
    inline, so a cancel interrupts whatever the run is awaiting -- including a
    long LLM call or tool -- instead of taking effect only at the next stream
    part.
    """
    configurable: dict[str, Any] = {"thread_id": thread_id}
    if context:
        configurable.update(context)
    config = {"configurable": configurable}

    graph_input = _build_command(command) or input_data
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    partial = _PartialAssistantText()

    async def pump() -> None:
        completed = False
        run_error: Exception | None = None
        try:
            async with registry.thread_lock(thread_id):
                # Heal a prior cancellation that may still be finalizing in a
                # background task before this run appends another user turn.
                await _finalize_interrupted_run(graph, thread_id)
                async for namespace, mode, payload in graph.astream(
                    graph_input,
                    config=config,
                    stream_mode=list(RUN_STREAM_MODES),
                    subgraphs=True,
                ):
                    partial.observe(mode, payload)
                    await queue.put(
                        format_sse_event(
                            _event_name(mode, namespace),
                            _serialize(mode, payload),
                        )
                    )
            completed = True
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Graph run failed thread_id=%s: %s", thread_id, exc)
            run_error = exc
        finally:
            await _persist(
                _finish_run(
                    graph=graph,
                    registry=registry,
                    thread_id=thread_id,
                    completed=completed,
                    partial_text=partial.text(),
                    sync_thread=sync_thread,
                ),
                error_message=f"Failed to finalize graph run for {thread_id}",
            )
            # Finalize the checkpoint before exposing the terminal error. The
            # client responds to this frame by re-reading state; ordering it
            # first would race that read against interrupted-turn repair.
            if run_error is not None:
                await queue.put(format_sse_error(run_error))
            await queue.put(None)

    task = asyncio.create_task(pump())
    if not registry.register(thread_id, task):
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        yield format_sse_error(RuntimeError(_CONCURRENT_RUN_NOTICE))
        return
    try:
        while True:
            frame = await queue.get()
            if frame is None:
                break
            yield frame
        # Surface a crash that happened after the sentinel was queued.
        if task.done() and not task.cancelled():
            exc = task.exception()
            if exc is not None:
                yield format_sse_error(exc)
    except (asyncio.CancelledError, GeneratorExit):
        # Client disconnected: stop the graph rather than letting it run on.
        task.cancel()
        raise
    finally:
        registry.unregister(thread_id, task)
        if not task.done():
            task.cancel()


async def fork_before_message(
    *,
    graph: Any,
    thread_id: str,
    message_id: str,
) -> bool:
    """Rewind a thread's checkpoint to just before ``message_id``.

    Backs message editing. LangGraph checkpoints are append-only, so editing a
    turn means forking history rather than mutating it: find the last snapshot
    that does NOT yet contain the message, then write it back as the new head.
    A subsequent run continues from there, which is what makes the superseded
    answer disappear instead of a second one appearing beside it.

    Returns ``False`` when the message is not in this thread's history, so the
    caller can fall back to appending.
    """
    # ``checkpoint_id``/``checkpoint_ns`` must be absent: with either set,
    # aget_state_history filters to that single pinned checkpoint and the walk
    # below never finds the message.
    history_config = {"configurable": {"thread_id": thread_id}}

    snapshots = [snapshot async for snapshot in graph.aget_state_history(history_config)]
    snapshots.reverse()  # oldest first

    target_index = next(
        (
            index
            for index, snapshot in enumerate(snapshots)
            if any(
                getattr(message, "id", None) == message_id
                for message in (snapshot.values or {}).get("messages", [])
            )
        ),
        None,
    )
    if target_index is None:
        return False

    if target_index == 0:
        # Nothing precedes it: fork to an empty thread rather than reusing the
        # snapshot, whose values are an alias we must not mutate in place.
        await graph.aupdate_state(history_config, {"messages": []}, as_node="__start__")
        return True

    before = snapshots[target_index - 1]
    next_nodes = before.next or ()
    if len(next_nodes) > 1:
        logger.warning(
            "Fork point for %s has multiple next nodes %r; forking at %r only",
            message_id,
            next_nodes,
            next_nodes[0],
        )
    await graph.aupdate_state(
        before.config,
        before.values,
        as_node=next_nodes[0] if next_nodes else "__start__",
    )
    return True
