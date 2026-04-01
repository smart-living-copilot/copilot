import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from copilot.graph.nodes import _make_router_messages, _sanitize_message_sequence


class NodeMessageSanitizationTestCase(unittest.TestCase):
    def test_sanitize_message_sequence_drops_orphan_tool_messages(self) -> None:
        messages = [
            HumanMessage(content="First request"),
            AIMessage(content="", tool_calls=[{"name": "things_search", "args": {}, "id": "call_1"}]),
            ToolMessage(content='[{"id":"thing-1"}]', tool_call_id="call_1"),
            AIMessage(content="Found the thing."),
            ToolMessage(content='{"unexpected":true}', tool_call_id="orphan"),
            HumanMessage(content="Second request"),
            AIMessage(content="", tool_calls=[{"name": "wot_get_action", "args": {}, "id": "call_2"}]),
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
            AIMessage(content="", tool_calls=[{"name": "things_search", "args": {}, "id": "call_1"}]),
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


if __name__ == "__main__":
    unittest.main()
