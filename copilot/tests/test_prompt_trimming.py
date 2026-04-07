import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from copilot.graph.nodes import _make_router_messages, _trim_conversation


def _tool_call(tool_id: str) -> dict:
    return {
        "id": tool_id,
        "name": "run_code",
        "args": {"code": "print('hello')"},
        "type": "tool_call",
    }


class PromptTrimmingTestCase(unittest.TestCase):
    def test_trim_conversation_preserves_tool_context(self) -> None:
        """Tool calls and results from all turns should survive trimming."""
        messages = [
            HumanMessage(content="Show the last 24h"),
            AIMessage(content="", tool_calls=[_tool_call("call-old")]),
            ToolMessage(content='{"rows":[1,2,3]}', tool_call_id="call-old"),
            AIMessage(content="Here is the 24h summary."),
            HumanMessage(content="Now compare with the last 48h"),
            AIMessage(content="", tool_calls=[_tool_call("call-current")]),
            ToolMessage(content='{"rows":[4,5,6]}', tool_call_id="call-current"),
        ]

        trimmed = _trim_conversation(messages, max_tokens=10_000)

        types = [type(m).__name__ for m in trimmed]
        self.assertEqual(
            types,
            [
                "HumanMessage",
                "AIMessage",
                "ToolMessage",
                "AIMessage",
                "HumanMessage",
                "AIMessage",
                "ToolMessage",
            ],
        )

    def test_router_messages_strip_tool_context(self) -> None:
        """The router should only see conversational messages."""
        messages = [
            HumanMessage(content="Show the last 24h"),
            AIMessage(content="", tool_calls=[_tool_call("call-old")]),
            ToolMessage(content='{"rows":[1,2,3]}', tool_call_id="call-old"),
            AIMessage(content="Energy use over the last 24h is 10 kWh."),
            HumanMessage(content="and the last 72h?"),
        ]

        tail = _make_router_messages(messages, max_tokens=10_000)

        # Router strips tool messages and AI messages with tool_calls
        self.assertTrue(all(not isinstance(m, ToolMessage) for m in tail))
        self.assertTrue(
            all(not (isinstance(m, AIMessage) and m.tool_calls) for m in tail),
        )
        # Should keep the conversational messages
        contents = [m.content for m in tail]
        self.assertIn("and the last 72h?", contents)


if __name__ == "__main__":
    unittest.main()
