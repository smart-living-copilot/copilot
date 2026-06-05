import json
import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from copilot.panels.edit import _extract_updated_panel


class ExtractUpdatedPanelTestCase(unittest.TestCase):
    def test_extracts_latest_html_and_capabilities(self) -> None:
        messages = [
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
            ToolMessage(
                tool_call_id="call_1",
                content=json.dumps(
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
                ),
            ),
        ]
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


if __name__ == "__main__":
    unittest.main()
