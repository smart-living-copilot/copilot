import asyncio
import unittest

from copilot.agent.tools.wot_registry import things_search
from copilot.search import set_active_search_service


class RegistryToolArgsTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        set_active_search_service(None)

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


if __name__ == "__main__":
    unittest.main()
