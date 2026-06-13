import asyncio
import json
import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from copilot.panels.edit import _extract_updated_panel, run_panel_edit


def _panel_tool_messages(content: str) -> list:
    return [
        HumanMessage(content="edit it"),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "create_web_interface",
                    "args": {"html": "<div>new</div>", "title": "P"},
                    "id": "call_1",
                }
            ],
        ),
        ToolMessage(tool_call_id="call_1", content=content),
    ]


class ExtractUpdatedPanelTestCase(unittest.TestCase):
    def test_run_panel_edit_formats_prompt_with_literal_binary_payload_shape(self) -> None:
        class FakeGraph:
            prompt = ""

            async def ainvoke(self, state, config):
                self.prompt = state["messages"][0].content
                self.config = config
                return {"messages": []}

        graph = FakeGraph()

        result = asyncio.run(
            run_panel_edit(
                graph=graph,
                checkpointer=None,
                html="<button>toggle</button>",
                capabilities=[],
                instruction="make the button blue",
            )
        )

        self.assertIsNone(result)
        self.assertIn('{ kind: "binary", contentType, bodyBase64,', graph.prompt)
        self.assertEqual(graph.config["configurable"]["thread_id"][:11], "panel-edit-")

    def test_extracts_latest_html_and_capabilities(self) -> None:
        messages = _panel_tool_messages(
            json.dumps(
                {
                    "artifacts": [
                        {
                            "ref": "ui_1",
                            "kind": "web",
                            "filename": "x.html",
                            "capabilities": [{"thingId": "urn:lamp", "ops": ["writeProperty"]}],
                        }
                    ]
                }
            )
        )
        result = _extract_updated_panel(messages)
        self.assertIsNotNone(result)
        html, caps = result
        self.assertEqual(html, "<div>new</div>")
        self.assertEqual(caps, [{"thingId": "urn:lamp", "ops": ["writeProperty"]}])

    def test_returns_none_when_no_tool_call(self) -> None:
        messages = [
            HumanMessage(content="edit it"),
            AIMessage(content="I cannot do that"),
        ]
        self.assertIsNone(_extract_updated_panel(messages))

    def test_returns_none_when_tool_result_is_not_json(self) -> None:
        self.assertIsNone(_extract_updated_panel(_panel_tool_messages("plain text failure")))

    def test_returns_none_when_artifact_is_not_mapping(self) -> None:
        self.assertIsNone(
            _extract_updated_panel(_panel_tool_messages(json.dumps({"artifacts": ["broken"]})))
        )


if __name__ == "__main__":
    unittest.main()
