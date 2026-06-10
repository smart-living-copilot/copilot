import asyncio
import unittest
from unittest.mock import patch

from copilot.agent.tools.wot_registry import REGISTRY_TOOLS, sparql_query, things_search
from copilot.search import set_active_search_service


class RegistryToolArgsTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        set_active_search_service(None)

    def test_registry_tools_include_sparql_query(self) -> None:
        tool_names = {tool.name for tool in REGISTRY_TOOLS}
        self.assertIn("sparql_query", tool_names)
        self.assertNotIn("things_sparql", tool_names)
        schema = sparql_query.args_schema.model_json_schema()
        self.assertIn("intent", schema["properties"])
        self.assertNotIn("query", schema["properties"])

    def test_things_search_clamps_out_of_range_k(self) -> None:
        class FakeSearchService:
            def __init__(self) -> None:
                self.calls: list[tuple[str, int]] = []

            async def search(self, *, query: str, k: int):
                self.calls.append((query, k))
                return []

        service = FakeSearchService()
        set_active_search_service(service)  # type: ignore[arg-type]

        high = asyncio.run(things_search.ainvoke({"query": "temperature", "k": 50}))
        low = asyncio.run(things_search.ainvoke({"query": "temperature", "k": 0}))

        self.assertEqual(high["k"], 20)
        self.assertEqual(low["k"], 1)
        self.assertEqual(service.calls, [("temperature", 20), ("temperature", 1)])

    def test_things_search_returns_tool_error_for_empty_query(self) -> None:
        response = asyncio.run(things_search.ainvoke({"query": "   ", "k": 5}))

        self.assertEqual(
            response,
            {"error": "query must not be empty", "items": [], "query": ""},
        )

    def test_sparql_query_runs_subgraph(self) -> None:
        calls = []

        async def fake_run_sparql_query_subgraph(**kwargs):
            calls.append(kwargs)
            return {
                "status": "ok",
                "intent": kwargs["intent"],
                "query": "SELECT * WHERE { ?s ?p ?o }",
                "endpoints": kwargs["endpoints"],
                "attempts": [],
                "summary": "Done",
                "result": {
                    "type": "select",
                    "rows": [],
                    "truncated": False,
                },
            }

        with patch(
            "copilot.agent.tools.wot_registry.run_sparql_query_subgraph",
            side_effect=fake_run_sparql_query_subgraph,
        ), patch(
            "copilot.agent.tools.wot_registry.make_llm",
            return_value=object(),
        ):
            response = asyncio.run(
                sparql_query.ainvoke(
                    {
                        "intent": " Find sensors with observations ",
                        "endpoints": [
                            " urn:slc:endpoint:one ",
                            "urn:slc:endpoint:one",
                            "urn:slc:endpoint:two",
                        ],
                        "limit": 999,
                    }
                )
            )

        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["summary"], "Done")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["intent"], "Find sensors with observations")
        self.assertEqual(calls[0]["limit"], 500)
        self.assertEqual(calls[0]["endpoints"], ["urn:slc:endpoint:one", "urn:slc:endpoint:two"])
        self.assertEqual(calls[0]["max_attempts"], 3)

    def test_sparql_query_returns_tool_error_for_empty_query(self) -> None:
        response = asyncio.run(sparql_query.ainvoke({"intent": "   ", "limit": 5}))

        self.assertEqual(response, {"error": "intent must not be empty", "intent": ""})

    def test_sparql_query_returns_tool_error_for_subgraph_errors(self) -> None:
        async def fake_run_sparql_query_subgraph(**_kwargs):
            raise ValueError("subgraph failed")

        with patch(
            "copilot.agent.tools.wot_registry.run_sparql_query_subgraph",
            side_effect=fake_run_sparql_query_subgraph,
        ), patch(
            "copilot.agent.tools.wot_registry.make_llm",
            return_value=object(),
        ):
            response = asyncio.run(
                sparql_query.ainvoke(
                    {
                        "intent": "Find Things",
                        "limit": 5,
                    }
                )
            )

        self.assertEqual(
            response,
            {
                "status": "failed",
                "error": "subgraph failed",
                "intent": "Find Things",
                "query": "",
                "limit": 5,
                "endpoints": [],
                "attempts": [],
                "summary": "SPARQL query failed: subgraph failed",
                "result": None,
            },
        )


if __name__ == "__main__":
    unittest.main()
