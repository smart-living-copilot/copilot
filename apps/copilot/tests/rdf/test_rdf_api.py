from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from copilot.rdf import api as rdf_api
from copilot.rdf.models import RdfQueryRequest


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

    with (
        patch("copilot.rdf.api.verify_internal_api_key"),
        patch(
            "copilot.rdf.api._service_rewrites",
            return_value={},
        ),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await rdf_api.query_rdf(request, payload)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {
        "category": "syntax",
        "message": "SyntaxError: Unknown prefix: wd",
        "retryable": True,
    }


def test_federation_proxy_rejects_non_loopback_callers() -> None:
    request = SimpleNamespace(client=SimpleNamespace(host="10.0.0.4"))
    settings = SimpleNamespace(RDF_FEDERATION_PROXY_LOOPBACK_ONLY=True)

    with pytest.raises(HTTPException) as exc_info:
        rdf_api._enforce_loopback_proxy_caller(request, settings)  # type: ignore[arg-type]

    assert exc_info.value.status_code == 403


def test_federation_proxy_allows_loopback_callers() -> None:
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    settings = SimpleNamespace(RDF_FEDERATION_PROXY_LOOPBACK_ONLY=True)

    rdf_api._enforce_loopback_proxy_caller(request, settings)  # type: ignore[arg-type]
