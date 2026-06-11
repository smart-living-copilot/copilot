import unittest
from types import SimpleNamespace
from unittest.mock import patch

from copilot.agent.builder import build_graph


def _tool(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


class BuilderVirtualToolsTestCase(unittest.TestCase):
    def test_control_branch_includes_virtual_thing_tools(self) -> None:
        captured: dict[str, list[str]] = {}

        def fake_make_control_node(_llm, tools, _max_tokens, **_kwargs):
            captured["control"] = [tool.name for tool in tools]
            return lambda state: state

        with (
            patch("copilot.agent.builder.make_router_node", return_value=lambda state: state),
            patch("copilot.agent.builder.make_respond_node", return_value=lambda state: state),
            patch("copilot.agent.builder.make_jobs_node", return_value=lambda state: state),
            patch("copilot.agent.builder.make_analysis_node", return_value=lambda state: state),
            patch("copilot.agent.builder.make_control_node", side_effect=fake_make_control_node),
            patch("copilot.agent.builder.ToolNode", return_value=lambda state: state),
        ):
            build_graph(
                llm=SimpleNamespace(),
                registry_tools=[
                    _tool("things_search"),
                    _tool("things_get"),
                    _tool("things_upsert"),
                    _tool("wot_read_property"),
                    _tool("wot_invoke_action"),
                ],
                local_tools=[
                    _tool("run_code"),
                    _tool("get_current_time"),
                    _tool("define_virtual_thing"),
                    _tool("delete_virtual_thing"),
                ],
                max_tokens=1000,
            )

        self.assertIn("define_virtual_thing", captured["control"])
        self.assertIn("delete_virtual_thing", captured["control"])


if __name__ == "__main__":
    unittest.main()
