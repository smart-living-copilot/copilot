"""Wire-format tests for the ``useStream`` chat transport.

These pin the contract that ``FetchStreamTransport``/``useStream`` in
``@langchain/langgraph-sdk`` imposes on our SSE endpoint. Getting any of this
subtly wrong produces a chat UI that silently renders nothing, so the shape is
asserted here rather than discovered in the browser.
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any, TypedDict

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    ToolMessage,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages

from wotbot.threads.runs import (
    RunRegistry,
    _interrupted_turn_updates,
    _event_name,
    fork_before_message,
    stream_run,
)


def _noop_sync(*_args, **_kwargs):
    return None


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _State(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


def _build_graph(*, fail: bool = False, slow: bool = False):
    model = GenericFakeChatModel(messages=iter([AIMessage(content="hello world")]))

    async def node(state: _State) -> dict[str, Any]:
        if fail:
            raise RuntimeError("boom")
        if slow:
            await asyncio.sleep(30)
        chunks = [chunk async for chunk in model.astream(state["messages"])]
        merged = chunks[0]
        for chunk in chunks[1:]:
            merged = merged + chunk
        return {"messages": [merged]}

    graph = StateGraph(_State)
    graph.add_node("respond", node)
    graph.add_edge(START, "respond")
    return graph.compile(checkpointer=InMemorySaver())


def _parse_sse(frames: list[str]) -> list[tuple[str, Any]]:
    """Decode frames the way the client's SSEDecoder does.

    Lines starting with ":" are comments and are dropped, and ``data`` is
    always ``JSON.parse``d -- so a non-JSON data payload would be a hard client
    error, not a soft one.
    """
    events: list[tuple[str, Any]] = []
    for frame in frames:
        event = None
        data_lines: list[str] = []
        for line in frame.split("\n"):
            if not line or line.startswith(":"):
                continue
            field, _, value = line.partition(":")
            value = value[1:] if value.startswith(" ") else value
            if field == "event":
                event = value
            elif field == "data":
                data_lines.append(value)
        if event is not None:
            events.append((event, json.loads("".join(data_lines)) if data_lines else None))
    return events


async def _collect(graph, **kwargs) -> list[tuple[str, Any]]:
    registry = RunRegistry()
    frames = [
        frame
        async for frame in stream_run(
            graph=graph,
            registry=registry,
            thread_id="t1",
            input_data={"messages": [("human", "hi")]},
            context=None,
            command=None,
            sync_thread=_noop_sync,
            **kwargs,
        )
    ]
    return _parse_sse(frames)


def test_event_name_is_bare_mode_at_root():
    assert _event_name("messages", ()) == "messages"
    assert _event_name("values", None) == "values"


def test_event_name_appends_pipe_separated_namespace():
    # The client recovers this with event.split("|").slice(1).
    assert _event_name("messages", ("router:abc",)) == "messages|router:abc"
    assert _event_name("updates", ("a", "b")) == "updates|a|b"


@pytest.mark.anyio
async def test_stream_emits_values_updates_and_messages():
    events = await _collect(_build_graph())
    names = {name for name, _ in events}
    assert "values" in names
    assert "updates" in names
    assert "messages" in names


@pytest.mark.anyio
async def test_messages_payload_is_two_element_array():
    """The client destructures ``const [serialized, metadata] = data``."""
    events = await _collect(_build_graph())
    payloads = [data for name, data in events if name == "messages"]
    assert payloads, "expected at least one messages frame"
    for payload in payloads:
        assert isinstance(payload, list)
        assert len(payload) == 2
        chunk, metadata = payload
        assert isinstance(chunk, dict)
        assert isinstance(metadata, dict)
        # The client switches on this, normalizing "AIMessageChunk" -> "ai".
        assert "type" in chunk
        assert metadata.get("langgraph_node") == "respond"


@pytest.mark.anyio
async def test_values_payload_carries_full_state():
    events = await _collect(_build_graph())
    values = [data for name, data in events if name == "values"]
    assert values
    assert "messages" in values[-1]


@pytest.mark.anyio
async def test_graph_failure_emits_terminal_error_frame():
    """The client builds StreamError from this instead of seeing a dropped socket."""
    events = await _collect(_build_graph(fail=True))
    errors = [data for name, data in events if name == "error"]
    assert len(errors) == 1
    assert errors[0]["name"] == "RuntimeError"
    assert errors[0]["message"] == "boom"


@pytest.mark.anyio
async def test_graph_failure_repairs_checkpoint_before_error_is_exposed():
    graph = _build_graph(fail=True)
    registry = RunRegistry()
    frames = stream_run(
        graph=graph,
        registry=registry,
        thread_id="t-error-order",
        input_data={"messages": [("human", "hi")]},
        context=None,
        command=None,
        sync_thread=_noop_sync,
    )

    async for frame in frames:
        if any(name == "error" for name, _ in _parse_sse([frame])):
            messages = (
                await graph.aget_state({"configurable": {"thread_id": "t-error-order"}})
            ).values["messages"]
            assert isinstance(messages[-1], AIMessage)
            assert "interrupted" in messages[-1].content
            break
    else:
        pytest.fail("expected an error frame")


@pytest.mark.anyio
async def test_cancel_stops_an_in_flight_run():
    registry = RunRegistry()
    graph = _build_graph(slow=True)
    frames = stream_run(
        graph=graph,
        registry=registry,
        thread_id="t1",
        input_data={"messages": [("human", "hi")]},
        context=None,
        command=None,
        sync_thread=_noop_sync,
    )

    collected: list[str] = []

    async def drain() -> None:
        async for frame in frames:
            collected.append(frame)

    task = asyncio.create_task(drain())
    await asyncio.sleep(0.1)
    assert registry.cancel("t1") is True
    await asyncio.wait_for(task, timeout=5)

    messages = (await graph.aget_state({"configurable": {"thread_id": "t1"}})).values["messages"]
    assert isinstance(messages[-1], AIMessage)
    assert "interrupted" in messages[-1].content


@pytest.mark.anyio
async def test_second_run_is_rejected_without_replacing_cancel_target():
    registry = RunRegistry()
    graph = _build_graph(slow=True)
    first_frames = stream_run(
        graph=graph,
        registry=registry,
        thread_id="t-concurrent",
        input_data={"messages": [("human", "first")]},
        context=None,
        command=None,
        sync_thread=_noop_sync,
    )

    async def drain_first() -> None:
        async for _frame in first_frames:
            pass

    first_task = asyncio.create_task(drain_first())
    await asyncio.sleep(0.1)

    second_events = [
        event
        async for frame in stream_run(
            graph=graph,
            registry=registry,
            thread_id="t-concurrent",
            input_data={"messages": [("human", "second")]},
            context=None,
            command=None,
            sync_thread=_noop_sync,
        )
        for event in _parse_sse([frame])
    ]

    assert second_events == [
        (
            "error",
            {
                "message": "A response is already running for this thread.",
                "name": "RuntimeError",
            },
        )
    ]
    assert registry.cancel("t-concurrent") is True
    await asyncio.wait_for(first_task, timeout=5)
    assert registry._thread_locks == {}


@pytest.mark.anyio
async def test_failed_run_repairs_dangling_human_turn():
    graph = _build_graph(fail=True)

    events = await _collect(graph)

    assert any(name == "error" for name, _ in events)
    messages = (await graph.aget_state({"configurable": {"thread_id": "t1"}})).values["messages"]
    assert isinstance(messages[-1], AIMessage)
    assert "interrupted" in messages[-1].content


@pytest.mark.anyio
async def test_completed_run_syncs_thread_title():
    graph = _build_graph()
    synced: list[tuple[str, str | None]] = []

    def sync(thread_id: str, *, suggested_title: str | None = None):
        synced.append((thread_id, suggested_title))

    frames = [
        frame
        async for frame in stream_run(
            graph=graph,
            registry=RunRegistry(),
            thread_id="t-title",
            input_data={"messages": [("human", "Name this thread")]},
            context=None,
            command=None,
            sync_thread=sync,
        )
    ]

    assert frames
    assert synced == [("t-title", "Name this thread")]


def test_cancel_is_false_when_no_run_is_active():
    assert RunRegistry().cancel("nope") is False


def _build_checkpointed_graph():
    """Graph whose node echoes back, so each run adds a human+ai pair."""

    async def node(state: _State) -> dict[str, Any]:
        return {"messages": [AIMessage(content="ok")]}

    graph = StateGraph(_State)
    graph.add_node("respond", node)
    graph.add_edge(START, "respond")
    return graph.compile(checkpointer=InMemorySaver())


@pytest.mark.anyio
async def test_fork_before_message_rewinds_history():
    graph = _build_checkpointed_graph()
    config = {"configurable": {"thread_id": "t-fork"}}

    await graph.ainvoke({"messages": [HumanMessage(content="one", id="h1")]}, config)
    await graph.ainvoke({"messages": [HumanMessage(content="two", id="h2")]}, config)

    before = (await graph.aget_state(config)).values["messages"]
    assert [m.content for m in before] == ["one", "ok", "two", "ok"]

    forked = await fork_before_message(graph=graph, thread_id="t-fork", message_id="h2")
    assert forked is True

    after = (await graph.aget_state(config)).values["messages"]
    # The edited turn and everything after it are gone; the earlier turn stays.
    assert [m.content for m in after] == ["one", "ok"]


@pytest.mark.anyio
async def test_fork_before_first_message_empties_the_thread():
    graph = _build_checkpointed_graph()
    config = {"configurable": {"thread_id": "t-first"}}
    await graph.ainvoke({"messages": [HumanMessage(content="one", id="h1")]}, config)

    assert await fork_before_message(graph=graph, thread_id="t-first", message_id="h1") is True
    assert (await graph.aget_state(config)).values["messages"] == []


@pytest.mark.anyio
async def test_fork_returns_false_for_unknown_message():
    graph = _build_checkpointed_graph()
    config = {"configurable": {"thread_id": "t-unknown"}}
    await graph.ainvoke({"messages": [HumanMessage(content="one", id="h1")]}, config)

    assert await fork_before_message(graph=graph, thread_id="t-unknown", message_id="nope") is False
    # Untouched.
    assert len((await graph.aget_state(config)).values["messages"]) == 2


def _tool_call(call_id: str, name: str = "run_code") -> dict[str, Any]:
    return {"id": call_id, "name": name, "args": {}}


def test_unfinished_turn_ending_on_a_tool_result_is_closed():
    """Tools ran but the final answer never arrived."""
    updates = _interrupted_turn_updates(
        [
            HumanMessage(content="go", id="h1"),
            AIMessage(content="", tool_calls=[_tool_call("c1")], id="a1"),
            ToolMessage(content='{"ok":1}', tool_call_id="c1", id="t1"),
        ]
    )

    assert [type(message) for message in updates] == [AIMessage]
    assert "interrupted" in updates[0].content


def test_unanswered_tool_calls_are_paired_before_the_turn_is_closed():
    """Stopped between the model and the tool node, so the calls have no results.

    Without the stand-in results the UI derives "still executing" from the
    missing result and shows a spinner on every reload.
    """
    updates = _interrupted_turn_updates(
        [
            HumanMessage(content="go", id="h1"),
            AIMessage(
                content="",
                tool_calls=[_tool_call("c1"), _tool_call("c2")],
                id="a1",
            ),
        ]
    )

    assert [type(message) for message in updates] == [
        ToolMessage,
        ToolMessage,
        AIMessage,
    ]
    assert [message.tool_call_id for message in updates[:2]] == ["c1", "c2"]
    assert all("stopped" in message.content for message in updates[:2])


def test_only_unresolved_tool_calls_are_paired():
    updates = _interrupted_turn_updates(
        [
            HumanMessage(content="go", id="h1"),
            AIMessage(
                content="",
                tool_calls=[_tool_call("c1"), _tool_call("c2")],
                id="a1",
            ),
            ToolMessage(content='{"ok":1}', tool_call_id="c1", id="t1"),
        ]
    )

    tool_updates = [m for m in updates if isinstance(m, ToolMessage)]
    assert [m.tool_call_id for m in tool_updates] == ["c2"]


def test_a_closed_turn_needs_no_repair():
    """Keeps the proactive and reactive callers from doubling up."""
    assert (
        _interrupted_turn_updates(
            [
                HumanMessage(content="go", id="h1"),
                AIMessage(content="", tool_calls=[_tool_call("c1")], id="a1"),
                ToolMessage(content='{"ok":1}', tool_call_id="c1", id="t1"),
                AIMessage(content="all done", id="a2"),
            ]
        )
        == []
    )


def test_partial_text_is_preserved_over_the_generic_notice():
    updates = _interrupted_turn_updates(
        [HumanMessage(content="go", id="h1")],
        partial_text="  half an answer  ",
    )
    assert updates[0].content == "half an answer"


def test_a_thread_with_no_user_turn_is_left_alone():
    assert _interrupted_turn_updates([]) == []
    assert _interrupted_turn_updates([AIMessage(content="hi", id="a1")]) == []
