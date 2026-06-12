import json
import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from copilot.agent.device_interactions import DEVICE_INTERACTION_SUMMARY_TYPE
from copilot.agent.nodes import (
    _make_router_messages,
    _trim_conversation,
)


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

    def test_huge_wot_calls_payload_does_not_evict_the_human_turn(self) -> None:
        """A multi-MB wot_calls blob is stripped before counting, so the real
        conversation survives a tight token budget (regression for the thread
        that reset to a fresh greeting after a large analysis run)."""
        bulky_wot_calls = [
            {
                "type": "invoke_action",
                "thing_id": "urn:predict",
                "name": "predict",
                "input": [{"time": str(i), "value": i} for i in range(8000)],
            }
        ]
        tool_content = json.dumps({"stdout": "Fetched 6529 readings", "wot_calls": bulky_wot_calls})

        messages = [
            HumanMessage(content="Run all NILM models on the smart meter"),
            AIMessage(content="", tool_calls=[_tool_call("call-1")]),
            ToolMessage(content=tool_content, tool_call_id="call-1"),
        ]

        trimmed = _trim_conversation(messages, max_tokens=2_000)

        contents = [m.content for m in trimmed]
        self.assertIn("Run all NILM models on the smart meter", contents)
        tool_messages = [m for m in trimmed if isinstance(m, ToolMessage)]
        self.assertTrue(tool_messages, "the run_code tool result should survive trimming")
        self.assertNotIn("wot_calls", tool_messages[0].content)

    def test_ui_device_summary_messages_are_not_sent_to_llm_prompts(self) -> None:
        summary = AIMessage(
            content=json.dumps(
                {
                    "type": DEVICE_INTERACTION_SUMMARY_TYPE,
                    "interactions": [
                        {
                            "type": "read_property",
                            "thingId": "urn:meter",
                            "affordanceName": "power",
                            "ok": True,
                        }
                    ],
                }
            )
        )
        messages = [
            HumanMessage(content="Show power"),
            AIMessage(content="Power is 10 kW."),
            summary,
            HumanMessage(content="and yesterday?"),
        ]

        trimmed = _trim_conversation(messages, max_tokens=10_000)
        routed = _make_router_messages(messages, max_tokens=10_000)

        self.assertNotIn(summary, trimmed)
        self.assertNotIn(summary, routed)


if __name__ == "__main__":
    unittest.main()
