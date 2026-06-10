from __future__ import annotations

import pytest

from copilot.agent.sparql_subgraph import (
    SparqlDraft,
    SparqlSummary,
    _DRAFT_SYSTEM_PROMPT,
    run_sparql_query_subgraph,
)


class FakeStructuredRunnable:
    def __init__(self, llm: "FakeLLM", schema):
        self._llm = llm
        self._schema = schema

    async def ainvoke(self, messages):
        self._llm.prompts.append(messages)
        if self._schema is SparqlDraft:
            item = self._llm.drafts.pop(0)
            return SparqlDraft(**item)
        if self._schema is SparqlSummary:
            item = self._llm.summaries.pop(0) if self._llm.summaries else {"summary": "Done"}
            return SparqlSummary(**item)
        raise AssertionError("unexpected schema")


class FakeLLM:
    def __init__(
        self,
        *,
        drafts: list[dict[str, str]],
        summaries: list[dict[str, str]] | None = None,
    ) -> None:
        self.drafts = list(drafts)
        self.summaries = list(summaries or [])
        self.prompts = []

    def with_structured_output(self, schema):
        return FakeStructuredRunnable(self, schema)


class FakeRdfExecutor:
    def __init__(self, responses: list[dict[str, object] | Exception]) -> None:
        self.responses = list(responses)
        self.calls = []

    async def __call__(self, *, query: str, endpoints: list[str], limit: int):
        self.calls.append({"query": query, "endpoints": endpoints, "limit": limit})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _context_loader(endpoint_ids: list[str]) -> list[dict[str, object]]:
    return [
        {
            "id": endpoint_id,
            "title": "Endpoint",
            "description": "Fake endpoint",
            "prefixes": {"ex": "https://example.com/"},
            "exampleQueries": [
                {
                    "intent": "Find example rows",
                    "query": "SELECT ?x WHERE { SERVICE <endpoint> { ?x ?p ?o } }",
                }
            ],
        }
        for endpoint_id in endpoint_ids
    ]


def _select_result(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "type": "select",
        "query": "SELECT ?thing WHERE { ?thing ?p ?o }",
        "limit": 50,
        "variables": ["thing"],
        "rows": rows,
        "truncated": False,
    }


def test_sparql_draft_prompt_requires_prefix_declarations():
    assert "explicit PREFIX declarations" in _DRAFT_SYSTEM_PROMPT


@pytest.mark.anyio
async def test_sparql_subgraph_drafts_executes_and_summarizes_success():
    llm = FakeLLM(
        drafts=[{"query": "SELECT ?thing WHERE { ?thing ?p ?o }"}],
        summaries=[{"summary": "Found one thing."}],
    )
    executor = FakeRdfExecutor(
        [_select_result([{"thing": {"type": "uri", "value": "urn:thing:alpha"}}])]
    )

    response = await run_sparql_query_subgraph(
        intent="Find Things",
        endpoints=[],
        limit=50,
        max_attempts=3,
        llm=llm,
        rdf_executor=executor,
        endpoint_context_loader=_context_loader,
    )

    assert response["status"] == "ok"
    assert response["summary"] == "Found one thing."
    assert response["attempts"][0]["status"] == "ok"
    assert executor.calls == [
        {"query": "SELECT ?thing WHERE { ?thing ?p ?o }", "endpoints": [], "limit": 50}
    ]


@pytest.mark.anyio
async def test_sparql_subgraph_repairs_after_executor_error():
    llm = FakeLLM(
        drafts=[
            {"query": "SELECT WHERE { ?thing ?p ?o }"},
            {"query": "SELECT ?thing WHERE { ?thing ?p ?o }"},
        ],
        summaries=[{"summary": "Repaired and found one thing."}],
    )
    executor = FakeRdfExecutor(
        [
            ValueError("SyntaxError: expected variable"),
            _select_result([{"thing": {"type": "uri", "value": "urn:thing:alpha"}}]),
        ]
    )

    response = await run_sparql_query_subgraph(
        intent="Find Things",
        endpoints=[],
        limit=50,
        max_attempts=3,
        llm=llm,
        rdf_executor=executor,
        endpoint_context_loader=_context_loader,
    )

    assert response["status"] == "ok"
    assert [attempt["status"] for attempt in response["attempts"]] == ["error", "ok"]
    assert "SyntaxError" in response["attempts"][0]["error"]
    assert len(executor.calls) == 2


@pytest.mark.anyio
async def test_sparql_subgraph_repairs_empty_select_results():
    llm = FakeLLM(
        drafts=[
            {"query": "SELECT ?thing WHERE { ?thing a <https://example.com/Narrow> }"},
            {"query": "SELECT ?thing WHERE { ?thing ?p ?o }"},
        ],
        summaries=[{"summary": "Relaxed the query and found one thing."}],
    )
    executor = FakeRdfExecutor(
        [
            _select_result([]),
            _select_result([{"thing": {"type": "uri", "value": "urn:thing:alpha"}}]),
        ]
    )

    response = await run_sparql_query_subgraph(
        intent="Find Things",
        endpoints=[],
        limit=50,
        max_attempts=3,
        llm=llm,
        rdf_executor=executor,
        endpoint_context_loader=_context_loader,
    )

    assert response["status"] == "ok"
    assert [attempt["status"] for attempt in response["attempts"]] == ["empty", "ok"]


@pytest.mark.anyio
async def test_sparql_subgraph_stops_after_max_attempts():
    llm = FakeLLM(
        drafts=[
            {"query": "SELECT WHERE { ?thing ?p ?o }"},
            {"query": "SELECT ALSO BAD WHERE { ?thing ?p ?o }"},
        ]
    )
    executor = FakeRdfExecutor(
        [
            ValueError("SyntaxError: expected variable"),
            ValueError("SyntaxError: still broken"),
        ]
    )

    response = await run_sparql_query_subgraph(
        intent="Find Things",
        endpoints=[],
        limit=50,
        max_attempts=2,
        llm=llm,
        rdf_executor=executor,
        endpoint_context_loader=_context_loader,
    )

    assert response["status"] == "failed"
    assert len(response["attempts"]) == 2
    assert response["summary"] == "SPARQL query failed: SyntaxError: still broken"


@pytest.mark.anyio
async def test_sparql_subgraph_does_not_retry_ask_false():
    llm = FakeLLM(
        drafts=[{"query": "ASK WHERE { ?thing ?p ?o }"}],
        summaries=[{"summary": "The condition is false."}],
    )
    executor = FakeRdfExecutor(
        [
            {
                "type": "ask",
                "query": "ASK WHERE { ?thing ?p ?o }",
                "limit": 50,
                "boolean": False,
                "truncated": False,
            }
        ]
    )

    response = await run_sparql_query_subgraph(
        intent="Check whether anything exists",
        endpoints=[],
        limit=50,
        max_attempts=3,
        llm=llm,
        rdf_executor=executor,
        endpoint_context_loader=_context_loader,
    )

    assert response["status"] == "ok"
    assert response["attempts"] == [
        {
            "attempt": 1,
            "query": "ASK WHERE { ?thing ?p ?o }",
            "status": "ok",
            "result": {
                "type": "ask",
                "truncated": False,
                "boolean": False,
            },
        }
    ]
    assert len(executor.calls) == 1
