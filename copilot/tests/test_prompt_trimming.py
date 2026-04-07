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
    def test_trim_conversation_drops_historical_tool_context(self) -> None:
        messages = [
            HumanMessage(content="Show the last 24h"),
            AIMessage(content="", tool_calls=[_tool_call("call-old")]),
            ToolMessage(content='{"rows":[1,2,3]}', tool_call_id="call-old"),
            AIMessage(content="Here is the 24h summary."),
            AIMessage(content='{"intent":"analysis"}'),
            HumanMessage(content="Now compare with the last 48h"),
            AIMessage(content="", tool_calls=[_tool_call("call-current")]),
            ToolMessage(content='{"rows":[4,5,6]}', tool_call_id="call-current"),
            AIMessage(content=""),
        ]

        trimmed = _trim_conversation(messages, max_tokens=10_000)

        self.assertEqual(
            [type(message).__name__ for message in trimmed],
            [
                "HumanMessage",
                "AIMessage",
                "HumanMessage",
                "AIMessage",
                "ToolMessage",
            ],
        )
        self.assertEqual(trimmed[0].content, "Show the last 24h")
        self.assertEqual(trimmed[1].content, "Here is the 24h summary.")
        self.assertEqual(trimmed[2].content, "Now compare with the last 48h")
        self.assertEqual(trimmed[3].tool_calls[0]["id"], "call-current")
        self.assertEqual(trimmed[4].tool_call_id, "call-current")

    def test_router_messages_ignore_internal_assistant_artifacts(self) -> None:
        messages = [
            HumanMessage(content="Show the last 24h"),
            AIMessage(content='{"intent":"analysis"}'),
            AIMessage(content=""),
            AIMessage(content="Energy use over the last 24h is 10 kWh."),
            HumanMessage(content="and the last 72h?"),
        ]

        tail = _make_router_messages(messages, max_tokens=10_000)

        self.assertEqual(
            [message.content for message in tail],
            [
                "Show the last 24h",
                "Energy use over the last 24h is 10 kWh.",
                "and the last 72h?",
            ],
        )


if __name__ == "__main__":
    unittest.main()
