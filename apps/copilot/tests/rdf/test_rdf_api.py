from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from copilot.rdf import api as rdf_api
from copilot.rdf.endpoint_client import SparqlEndpoint
from copilot.rdf.models import RdfEndpointQueryRequest, RdfQueryRequest


@pytest.fixture
def anyio_backend():
    return "asyncio"


class RaisingRdfStore:
    async def query(self, **_kwargs):
        raise RuntimeError("SyntaxError: Unknown prefix: wd")


@pytest.mark.anyio
async def test_query_rdf_returns_structured_error_for_query_failures() -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(),
                rdf_store=RaisingRdfStore(),
            )
        )
    )
    payload = RdfQueryRequest(query="SELECT ?s WHERE { ?s ?p ?o }", limit=10)

    with patch("copilot.rdf.api.verify_internal_api_key"):
        with pytest.raises(HTTPException) as exc_info:
            await rdf_api.query_rdf(request, payload)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {
        "category": "syntax",
        "message": "SyntaxError: Unknown prefix: wd",
        "retryable": True,
    }


@pytest.mark.anyio
async def test_query_rdf_endpoint_resolves_endpoint_and_returns_results() -> None:
    settings = SimpleNamespace()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))
    service_query = """
        SELECT ?item WHERE {
            SERVICE <https://query.wikidata.org/sparql> {
                ?item ?p ?o .
            }
        }
    """
    endpoint = SparqlEndpoint(
        thing_id="urn:slc:endpoint:kg",
        endpoint_url="https://example.org/sparql",
        security_name=None,
        security_definition={"scheme": "nosec"},
        credential=None,
    )

    async def fake_query_sparql_endpoint(**kwargs):
        assert kwargs["query"] == service_query
        assert kwargs["endpoint"] == endpoint
        assert kwargs["settings"] == settings
        return {
            "endpoint_url": "https://example.org/sparql",
            "content_type": "application/sparql-results+json",
            "results": {"head": {"vars": ["s"]}, "results": {"bindings": []}},
        }

    with (
        patch("copilot.rdf.api.verify_internal_api_key"),
        patch("copilot.rdf.api._resolve_endpoint", return_value=endpoint),
        patch(
            "copilot.rdf.api.query_sparql_endpoint",
            side_effect=fake_query_sparql_endpoint,
        ),
    ):
        response = await rdf_api.query_rdf_endpoint(
            "urn:slc:endpoint:kg",
            request,  # type: ignore[arg-type]
            RdfEndpointQueryRequest(query=service_query, limit=10),
        )

    assert response == {
        "endpoint_id": "urn:slc:endpoint:kg",
        "endpoint_url": "https://example.org/sparql",
        "query": service_query,
        "limit": 10,
        "content_type": "application/sparql-results+json",
        "results": {"head": {"vars": ["s"]}, "results": {"bindings": []}},
    }
