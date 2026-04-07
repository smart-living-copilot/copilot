import unittest
from types import SimpleNamespace

from copilot.graph.tool_groups import group_local_tools, partition_mcp_tools


def _tool(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


class ToolGroupsTestCase(unittest.TestCase):
    def test_partition_mcp_tools_uses_explicit_name_groups(self) -> None:
        grouped = partition_mcp_tools(
            [
                _tool("things_search"),
                _tool("things_get"),
                _tool("wot_read_property"),
                _tool("wot_invoke_action"),
                _tool("unknown_tool"),
            ]
        )

        self.assertEqual(
            [tool.name for tool in grouped.discovery],
            ["things_search"],
        )
        self.assertEqual([tool.name for tool in grouped.inspect], ["things_get"])
        self.assertEqual(
            [tool.name for tool in grouped.runtime],
            ["wot_read_property", "wot_invoke_action"],
        )
        self.assertEqual(
            [tool.name for tool in grouped.runtime_read],
            ["wot_read_property"],
        )
        self.assertEqual(
            [tool.name for tool in grouped.discovery_and_inspect],
            ["things_search", "things_get"],
        )

    def test_group_local_tools_requires_expected_tools(self) -> None:
        grouped = group_local_tools(
            [
                _tool("run_code"),
                _tool("get_current_time"),
                _tool("create_job"),
                _tool("create_analysis_job"),
                _tool("list_jobs"),
                _tool("run_job_now"),
            ]
        )

        self.assertEqual(grouped.run_code.name, "run_code")
        self.assertEqual(grouped.get_current_time.name, "get_current_time")
        self.assertEqual(
            [tool.name for tool in grouped.job_tools],
            ["create_job", "create_analysis_job", "list_jobs", "run_job_now"],
        )

    def test_group_local_tools_raises_when_required_tool_is_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, "get_current_time"):
            group_local_tools([_tool("run_code")])


if __name__ == "__main__":
    unittest.main()
