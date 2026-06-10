import asyncio
import unittest
from unittest.mock import patch

from copilot.agent.tools.wot_registry import REGISTRY_TOOLS, things_search, things_sparql
from copilot.search import set_active_search_service


class RegistryToolArgsTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        set_active_search_service(None)

    def test_registry_tools_include_things_sparql(self) -> None:
        self.assertIn("things_sparql", {tool.name for tool in REGISTRY_TOOLS})

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

    def test_things_sparql_uses_rdf_service_client(self) -> None:
        calls = []

        class FakeRdfClient:
            async def query(self, *, query: str, limit: int, use_default_graph_as_union: bool):
                calls.append((query, limit, use_default_graph_as_union))
                return {
                    "type": "select",
                    "query": query,
                    "limit": limit,
                    "variables": ["thing"],
                    "rows": [],
                    "truncated": False,
                }

        with patch(
            "copilot.agent.tools.wot_registry._rdf_client",
            return_value=FakeRdfClient(),
        ):
            response = asyncio.run(
                things_sparql.ainvoke(
                    {
                        "query": " SELECT * WHERE { ?s ?p ?o } ",
                        "limit": 999,
                    }
                )
            )

        self.assertEqual(response["type"], "select")
        self.assertEqual(response["limit"], 500)
        self.assertEqual(calls, [("SELECT * WHERE { ?s ?p ?o }", 500, True)])

    def test_things_sparql_returns_tool_error_for_empty_query(self) -> None:
        response = asyncio.run(things_sparql.ainvoke({"query": "   ", "limit": 5}))

        self.assertEqual(response, {"error": "query must not be empty", "query": ""})

    def test_things_sparql_returns_tool_error_for_service_errors(self) -> None:
        class FakeRdfClient:
            async def query(self, *, query: str, limit: int, use_default_graph_as_union: bool):
                raise ValueError("Only read-only SPARQL queries are allowed")

        with patch(
            "copilot.agent.tools.wot_registry._rdf_client",
            return_value=FakeRdfClient(),
        ):
            response = asyncio.run(
                things_sparql.ainvoke(
                    {
                        "query": "DELETE WHERE { ?s ?p ?o }",
                        "limit": 5,
                    }
                )
            )

        self.assertEqual(
            response,
            {
                "error": "Only read-only SPARQL queries are allowed",
                "query": "DELETE WHERE { ?s ?p ?o }",
                "limit": 5,
            },
        )


if __name__ == "__main__":
    unittest.main()
