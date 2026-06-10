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


def _context_loader() -> list[dict[str, object]]:
    return [
        {
            "id": "urn:slc:endpoint:kg",
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
        limit=50,
        llm=llm,
        rdf_executor=executor,
        endpoint_context_loader=_context_loader,
    )

    assert response["status"] == "ok"
    assert response["summary"] == "Found one thing."
    assert response["selected_endpoints"] == []
    assert response["attempts"][0]["status"] == "ok"
    assert executor.calls == [
        {"query": "SELECT ?thing WHERE { ?thing ?p ?o }", "endpoints": [], "limit": 50}
    ]


@pytest.mark.anyio
async def test_sparql_subgraph_selects_generated_service_endpoints():
    llm = FakeLLM(
        drafts=[
            {
                "query": (
                    "SELECT ?x WHERE { "
                    "SERVICE <urn:slc:endpoint:kg> { ?x <https://example.com/p> ?o } "
                    "}"
                )
            }
        ],
        summaries=[{"summary": "Found remote rows."}],
    )
    executor = FakeRdfExecutor(
        [_select_result([{"x": {"type": "uri", "value": "https://example.com/x"}}])]
    )

    response = await run_sparql_query_subgraph(
        intent="Find remote rows",
        limit=25,
        llm=llm,
        rdf_executor=executor,
        endpoint_context_loader=_context_loader,
    )

    assert response["status"] == "ok"
    assert response["selected_endpoints"] == ["urn:slc:endpoint:kg"]
    assert executor.calls == [
        {
            "query": (
                "SELECT ?x WHERE { "
                "SERVICE <urn:slc:endpoint:kg> { ?x <https://example.com/p> ?o } "
                "}"
            ),
            "endpoints": ["urn:slc:endpoint:kg"],
            "limit": 25,
        }
    ]


@pytest.mark.anyio
async def test_sparql_subgraph_prompt_includes_discovered_endpoint_context():
    llm = FakeLLM(
        drafts=[{"query": "SELECT ?thing WHERE { ?thing ?p ?o }"}],
        summaries=[{"summary": "Done."}],
    )
    executor = FakeRdfExecutor([_select_result([])])

    await run_sparql_query_subgraph(
        intent="Find Things",
        limit=50,
        llm=llm,
        rdf_executor=executor,
        endpoint_context_loader=_context_loader,
    )

    draft_payload = llm.prompts[0][1].content
    assert "available_endpoints" in draft_payload
    assert "urn:slc:endpoint:kg" in draft_payload


@pytest.mark.anyio
async def test_sparql_subgraph_reports_unknown_service_endpoint_error_without_retry():
    llm = FakeLLM(
        drafts=[
            {
                "query": (
                    "SELECT ?x WHERE { "
                    "SERVICE <urn:slc:endpoint:unknown> { ?x ?p ?o } "
                    "}"
                )
            }
        ],
    )
    executor = FakeRdfExecutor([ValueError("SPARQL SERVICE targets must be declared endpoint Thing ids passed in endpoints")])

    response = await run_sparql_query_subgraph(
        intent="Find remote rows",
        limit=50,
        llm=llm,
        rdf_executor=executor,
        endpoint_context_loader=_context_loader,
    )

    assert response["status"] == "failed"
    assert response["selected_endpoints"] == []
    assert len(executor.calls) == 1
    assert executor.calls[0]["endpoints"] == []
    assert "endpoint Thing ids" in response["attempts"][0]["error"]


@pytest.mark.anyio
async def test_sparql_subgraph_returns_executor_error_without_retry():
    llm = FakeLLM(
        drafts=[{"query": "SELECT WHERE { ?thing ?p ?o }"}],
    )
    executor = FakeRdfExecutor([ValueError("SyntaxError: expected variable")])

    response = await run_sparql_query_subgraph(
        intent="Find Things",
        limit=50,
        llm=llm,
        rdf_executor=executor,
        endpoint_context_loader=_context_loader,
    )

    assert response["status"] == "failed"
    assert [attempt["status"] for attempt in response["attempts"]] == ["error"]
    assert "SyntaxError" in response["attempts"][0]["error"]
    assert response["summary"] == "SPARQL query failed: SyntaxError: expected variable"
    assert len(executor.calls) == 1


@pytest.mark.anyio
async def test_sparql_subgraph_treats_empty_select_as_success():
    llm = FakeLLM(
        drafts=[{"query": "SELECT ?thing WHERE { ?thing a <https://example.com/Narrow> }"}],
        summaries=[{"summary": "No matching things were found."}],
    )
    executor = FakeRdfExecutor([_select_result([])])

    response = await run_sparql_query_subgraph(
        intent="Find Things",
        limit=50,
        llm=llm,
        rdf_executor=executor,
        endpoint_context_loader=_context_loader,
    )

    assert response["status"] == "ok"
    assert response["summary"] == "No matching things were found."
    assert [attempt["status"] for attempt in response["attempts"]] == ["ok"]
    assert response["attempts"][0]["result"]["row_count"] == 0
    assert len(executor.calls) == 1


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
        limit=50,
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
