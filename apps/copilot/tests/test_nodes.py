import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from copilot.agent.nodes import (
    IntentClassification,
    _make_llm_node,
    _make_router_messages,
    _sanitize_message_sequence,
    _strip_wot_calls,
)


def _tool(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


class _FakeBoundLLM:
    def __init__(self, parent: "_FakeLLM") -> None:
        self._parent = parent

    async def ainvoke(self, messages):
        self._parent.invocations.append(("bound", messages))
        return AIMessage(content="ok")


class _FakeLLM:
    def __init__(self) -> None:
        self.bound_tools: list[list[str]] = []
        self.bound_kwargs: list[dict] = []
        self.invocations: list[tuple[str, object]] = []

    def bind_tools(self, tools, **kwargs):
        self.bound_tools.append([tool.name for tool in tools])
        self.bound_kwargs.append(kwargs)
        return _FakeBoundLLM(self)

    async def ainvoke(self, messages):
        self.invocations.append(("plain", messages))
        return AIMessage(content="ok")


class NodeMessageSanitizationTestCase(unittest.TestCase):
    def test_router_schema_accepts_jobs_intent(self) -> None:
        self.assertEqual(IntentClassification(intent="jobs").intent, "jobs")

    def test_sanitize_message_sequence_drops_orphan_tool_messages(self) -> None:
        messages = [
            HumanMessage(content="First request"),
            AIMessage(
                content="", tool_calls=[{"name": "things_search", "args": {}, "id": "call_1"}]
            ),
            ToolMessage(content='[{"id":"thing-1"}]', tool_call_id="call_1"),
            AIMessage(content="Found the thing."),
            ToolMessage(content='{"unexpected":true}', tool_call_id="orphan"),
            HumanMessage(content="Second request"),
            AIMessage(
                content="", tool_calls=[{"name": "wot_get_action", "args": {}, "id": "call_2"}]
            ),
        ]

        sanitized = _sanitize_message_sequence(messages)

        self.assertEqual(
            sanitized,
            [
                messages[0],
                messages[1],
                messages[2],
                messages[3],
                messages[5],
            ],
        )

    def test_make_router_messages_filters_out_tool_turns(self) -> None:
        messages = [
            HumanMessage(content="Show me house 5 power"),
            AIMessage(
                content="", tool_calls=[{"name": "things_search", "args": {}, "id": "call_1"}]
            ),
            ToolMessage(content='[{"id":"meter-05"}]', tool_call_id="call_1"),
            AIMessage(content="I found the smart meter."),
            HumanMessage(content="Now disaggregate it with all NILM services."),
        ]

        router_messages = _make_router_messages(messages, max_tokens=4000)

        self.assertEqual(
            router_messages,
            [
                messages[0],
                messages[3],
                messages[4],
            ],
        )

    def test_sanitize_patches_ai_with_partial_tool_results(self) -> None:
        """AI made 2 tool calls but only 1 ToolMessage exists (trimmed parallel call)."""
        ai = AIMessage(
            content="",
            tool_calls=[
                {"name": "wot_get_action", "args": {}, "id": "call_a"},
                {"name": "wot_get_action", "args": {}, "id": "call_b"},
            ],
            additional_kwargs={
                "tool_calls": [
                    {
                        "id": "call_a",
                        "type": "function",
                        "function": {"name": "wot_get_action", "arguments": "{}"},
                    },
                    {
                        "id": "call_b",
                        "type": "function",
                        "function": {"name": "wot_get_action", "arguments": "{}"},
                    },
                ]
            },
        )
        messages = [
            HumanMessage(content="Inspect both"),
            ai,
            ToolMessage(content='{"schema": "ok"}', tool_call_id="call_a"),
        ]

        sanitized = _sanitize_message_sequence(messages)

        self.assertEqual(len(sanitized), 3)
        # AI message should be patched to only reference call_a
        self.assertEqual(len(sanitized[1].tool_calls), 1)
        self.assertEqual(sanitized[1].tool_calls[0]["id"], "call_a")
        self.assertEqual(len(sanitized[1].additional_kwargs["tool_calls"]), 1)

    def test_sanitize_does_not_mutate_ai_messages_when_patching(self) -> None:
        ai = AIMessage(
            content="",
            tool_calls=[
                {"name": "wot_get_action", "args": {}, "id": "call_a"},
                {"name": "wot_get_action", "args": {}, "id": "call_b"},
            ],
            additional_kwargs={
                "tool_calls": [
                    {
                        "id": "call_a",
                        "type": "function",
                        "function": {"name": "wot_get_action", "arguments": "{}"},
                    },
                    {
                        "id": "call_b",
                        "type": "function",
                        "function": {"name": "wot_get_action", "arguments": "{}"},
                    },
                ]
            },
        )

        _sanitize_message_sequence(
            [
                HumanMessage(content="Inspect both"),
                ai,
                ToolMessage(content='{"schema": "a"}', tool_call_id="call_a"),
            ]
        )

        self.assertEqual([call["id"] for call in ai.tool_calls], ["call_a", "call_b"])
        self.assertEqual(len(ai.additional_kwargs["tool_calls"]), 2)

    def test_sanitize_keeps_all_parallel_results(self) -> None:
        """AI made 2 tool calls and both ToolMessages exist — keep everything."""
        ai = AIMessage(
            content="",
            tool_calls=[
                {"name": "wot_get_action", "args": {}, "id": "call_a"},
                {"name": "wot_get_action", "args": {}, "id": "call_b"},
            ],
        )
        messages = [
            HumanMessage(content="Inspect both"),
            ai,
            ToolMessage(content='{"schema": "a"}', tool_call_id="call_a"),
            ToolMessage(content='{"schema": "b"}', tool_call_id="call_b"),
            AIMessage(content="Both inspected."),
        ]

        sanitized = _sanitize_message_sequence(messages)

        self.assertEqual(len(sanitized), 5)
        self.assertEqual(len(sanitized[1].tool_calls), 2)


class StripWotCallsTestCase(unittest.TestCase):
    def test_removes_wot_calls_from_json_tool_message(self) -> None:
        import json

        original = json.dumps(
            {
                "stdout": "hello",
                "artifacts": [{"ref": "chart_1", "kind": "plotly", "filename": "abc.json"}],
                "wot_calls": [{"type": "invoke_action", "thing_id": "urn:1", "name": "get_power"}],
            }
        )
        msg = ToolMessage(content=original, tool_call_id="call_1")
        result = _strip_wot_calls(msg)

        parsed = json.loads(result.content)
        self.assertIn("stdout", parsed)
        self.assertIn("artifacts", parsed)
        self.assertNotIn("wot_calls", parsed)

    def test_preserves_non_json_content(self) -> None:
        msg = ToolMessage(content="plain text result", tool_call_id="call_1")
        result = _strip_wot_calls(msg)
        self.assertEqual(result.content, "plain text result")

    def test_preserves_json_without_wot_calls(self) -> None:
        import json

        original = json.dumps({"stdout": "ok", "artifacts": []})
        msg = ToolMessage(content=original, tool_call_id="call_1")
        result = _strip_wot_calls(msg)
        self.assertEqual(result.content, original)

    def test_passes_through_non_tool_messages(self) -> None:
        msg = HumanMessage(content="hello")
        result = _strip_wot_calls(msg)
        self.assertIs(result, msg)

    def test_does_not_mutate_original_message(self) -> None:
        import json

        original = json.dumps({"stdout": "x", "wot_calls": [{"type": "read"}]})
        msg = ToolMessage(content=original, tool_call_id="call_1")
        _strip_wot_calls(msg)
        self.assertIn("wot_calls", msg.content)


class DynamicToolBindingTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_llm_node_filters_camera_tool_when_camera_is_inactive(self) -> None:
        llm = _FakeLLM()
        node = _make_llm_node(
            llm,
            tools=[_tool("get_current_time"), _tool("look_at_camera")],
            system_text="system",
            max_tokens=4000,
        )

        with patch("copilot.agent.nodes.is_look_at_camera_available", return_value=False):
            await node(
                {"messages": [HumanMessage(content="what is this?")]},
                {"configurable": {"thread_id": "thread-1"}},
            )

        self.assertEqual(llm.bound_tools, [["get_current_time"]])
        self.assertEqual(llm.invocations[0][0], "bound")

    async def test_llm_node_keeps_camera_tool_when_camera_is_active(self) -> None:
        llm = _FakeLLM()
        node = _make_llm_node(
            llm,
            tools=[_tool("get_current_time"), _tool("look_at_camera")],
            system_text="system",
            max_tokens=4000,
        )

        with patch("copilot.agent.nodes.is_look_at_camera_available", return_value=True):
            await node(
                {"messages": [HumanMessage(content="what is this?")]},
                {"configurable": {"thread_id": "thread-1"}},
            )

        self.assertEqual(llm.bound_tools, [["get_current_time", "look_at_camera"]])
        self.assertEqual(llm.invocations[0][0], "bound")

    async def test_llm_node_uses_plain_llm_when_camera_was_the_only_tool(self) -> None:
        llm = _FakeLLM()
        node = _make_llm_node(
            llm,
            tools=[_tool("look_at_camera")],
            system_text="system",
            max_tokens=4000,
        )

        with patch("copilot.agent.nodes.is_look_at_camera_available", return_value=False):
            await node(
                {"messages": [HumanMessage(content="what is this?")]},
                {"configurable": {"thread_id": "thread-1"}},
            )

        self.assertEqual(llm.bound_tools, [])
        self.assertEqual(llm.invocations[0][0], "plain")


if __name__ == "__main__":
    unittest.main()
