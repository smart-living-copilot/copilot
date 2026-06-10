from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from copilot.catalog.credentials.models import CredentialRecord
from copilot.rdf.endpoint_client import (
    SparqlEndpoint,
    build_endpoint_auth,
    build_endpoint_headers,
    endpoint_user_agent,
    endpoint_metadata_from_document,
    query_sparql_endpoint,
)


class Settings:
    RDF_ENDPOINT_ALLOWED_HOSTS = ""
    RDF_ENDPOINT_ALLOW_PRIVATE = False


def _settings(**values):
    return SimpleNamespace(
        RDF_ENDPOINT_ALLOWED_HOSTS=values.get("allowed_hosts", ""),
        RDF_ENDPOINT_ALLOW_PRIVATE=values.get("allow_private", False),
        RDF_ENDPOINT_USER_AGENT=values.get("user_agent", ""),
        RDF_ENDPOINT_TIMEOUT_SECONDS=values.get("timeout_seconds", 10),
        RDF_ENDPOINT_MAX_RESPONSE_BYTES=values.get("max_response_bytes", 2_000_000),
    )


def _endpoint_td(endpoint_url: str = "http://93.184.216.34/sparql") -> dict[str, object]:
    return {
        "@context": {
            "sd": "http://www.w3.org/ns/sparql-service-description#",
            "void": "http://rdfs.org/ns/void#",
        },
        "@type": ["sd:Service"],
        "id": "urn:slc:endpoint:energy",
        "title": "Energy KG",
        "securityDefinitions": {
            "sparql_auth": {
                "scheme": "bearer",
            }
        },
        "security": "sparql_auth",
        "sd:endpoint": {"@id": endpoint_url},
        "sd:supportedLanguage": {"@id": "sd:SPARQL11Query"},
        "void:vocabulary": [{"@id": "https://saref.etsi.org/core/"}],
    }


def _credential(
    scheme: str,
    credentials: dict[str, object],
    security_name: str = "sparql_auth",
) -> CredentialRecord:
    return CredentialRecord(
        id="credential-1",
        thing_id="urn:slc:endpoint:energy",
        security_name=security_name,
        scheme=scheme,
        credentials=credentials,
    )


def test_endpoint_metadata_accepts_standard_sd_endpoint_thing():
    metadata = endpoint_metadata_from_document(
        thing_id="urn:slc:endpoint:energy",
        document=_endpoint_td(),
        settings=Settings(),
    )

    assert metadata.endpoint_url == "http://93.184.216.34/sparql"
    assert metadata.security_name == "sparql_auth"
    assert metadata.scheme == "bearer"


def test_endpoint_metadata_rejects_missing_service_type():
    document = _endpoint_td()
    document["@type"] = ["Thing"]

    with pytest.raises(ValueError, match="sd:Service"):
        endpoint_metadata_from_document(
            thing_id="urn:slc:endpoint:energy",
            document=document,
            settings=Settings(),
        )


def test_endpoint_metadata_rejects_unsupported_url_scheme():
    with pytest.raises(ValueError, match="http or https"):
        endpoint_metadata_from_document(
            thing_id="urn:slc:endpoint:energy",
            document=_endpoint_td("ftp://example.com/sparql"),
            settings=Settings(),
        )


def test_endpoint_metadata_blocks_private_hosts_by_default():
    with pytest.raises(ValueError, match="private or reserved"):
        endpoint_metadata_from_document(
            thing_id="urn:slc:endpoint:energy",
            document=_endpoint_td("http://127.0.0.1:9999/sparql"),
            settings=Settings(),
        )


def test_endpoint_metadata_allows_private_hosts_when_opted_in():
    metadata = endpoint_metadata_from_document(
        thing_id="urn:slc:endpoint:energy",
        document=_endpoint_td("http://127.0.0.1:9999/sparql"),
        settings=_settings(allow_private=True),
    )

    assert metadata.endpoint_url == "http://127.0.0.1:9999/sparql"


def test_endpoint_metadata_allows_private_hosts_by_allowlist():
    metadata = endpoint_metadata_from_document(
        thing_id="urn:slc:endpoint:energy",
        document=_endpoint_td("http://127.0.0.1:9999/sparql"),
        settings=_settings(allowed_hosts="127.0.0.1:9999"),
    )

    assert metadata.endpoint_url == "http://127.0.0.1:9999/sparql"


def test_build_endpoint_auth_supports_bearer_basic_and_api_key():
    bearer_headers, bearer_params = build_endpoint_auth(
        security_definition={"scheme": "bearer"},
        credential=_credential("bearer", {"token": "secret-token"}),
    )
    assert bearer_headers == {"Authorization": "Bearer secret-token"}
    assert bearer_params == []

    basic_headers, basic_params = build_endpoint_auth(
        security_definition={"scheme": "basic"},
        credential=_credential(
            "basic",
            {
                "username": "demo",
                "password": "pass",
            },
        ),
    )
    encoded = base64.b64encode(b"demo:pass").decode("ascii")
    assert basic_headers == {"Authorization": f"Basic {encoded}"}
    assert basic_params == []

    api_key_headers, api_key_params = build_endpoint_auth(
        security_definition={"scheme": "apikey", "in": "header", "name": "X-API-Key"},
        credential=_credential("apikey", {"value": "key-1"}),
    )
    assert api_key_headers == {"X-API-Key": "key-1"}
    assert api_key_params == []

    query_headers, query_params = build_endpoint_auth(
        security_definition={"scheme": "apikey", "in": "query", "name": "api_key"},
        credential=_credential("apikey", {"api_key": "key-2"}),
    )
    assert query_headers == {}
    assert query_params == [("api_key", "key-2")]


def test_build_endpoint_auth_allows_nosec_without_credentials():
    headers, params = build_endpoint_auth(
        security_definition={"scheme": "nosec"},
        credential=None,
    )

    assert headers == {}
    assert params == []


def test_endpoint_user_agent_uses_default_when_setting_is_blank():
    assert endpoint_user_agent(_settings(user_agent="")).startswith("SmartLivingCopilot/")


def test_build_endpoint_headers_sends_configured_user_agent():
    headers = build_endpoint_headers(
        method="POST",
        request_headers={
            "accept": "application/sparql-results+json",
            "content-type": "application/sparql-query",
        },
        auth_headers={"Authorization": "Bearer token"},
        settings=_settings(user_agent="SmartLivingCopilotTest/1.0 (ops@example.test)"),
    )

    assert headers == {
        "Accept": "application/sparql-results+json",
        "Content-Type": "application/sparql-query",
        "User-Agent": "SmartLivingCopilotTest/1.0 (ops@example.test)",
        "Authorization": "Bearer token",
    }


class _FakeSparqlEndpoint(BaseHTTPRequestHandler):
    response_body: bytes = b"{}"
    response_status: int = 200
    response_content_type: str = "application/sparql-results+json"
    last_headers: dict[str, str] = {}
    last_query_params: dict[str, list[str]] = {}
    last_form: dict[str, list[str]] = {}

    def do_POST(self) -> None:
        length = int(self.headers.get("content-length") or "0")
        raw_body = self.rfile.read(length).decode("utf-8") if length else ""
        _FakeSparqlEndpoint.last_headers = dict(self.headers)
        _FakeSparqlEndpoint.last_query_params = parse_qs(urlsplit(self.path).query)
        _FakeSparqlEndpoint.last_form = parse_qs(raw_body)

        self.send_response(self.response_status)
        self.send_header("Content-Type", self.response_content_type)
        self.send_header("Content-Length", str(len(self.response_body)))
        self.end_headers()
        self.wfile.write(self.response_body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def _start_fake_sparql_endpoint(
    *,
    body: dict[str, object] | str,
    status: int = 200,
) -> tuple[ThreadingHTTPServer, str]:
    _FakeSparqlEndpoint.response_body = (
        json.dumps(body).encode("utf-8") if isinstance(body, dict) else body.encode("utf-8")
    )
    _FakeSparqlEndpoint.response_status = status
    _FakeSparqlEndpoint.last_headers = {}
    _FakeSparqlEndpoint.last_query_params = {}
    _FakeSparqlEndpoint.last_form = {}
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeSparqlEndpoint)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return server, f"http://{host}:{port}/sparql"


@pytest.mark.anyio
async def test_query_sparql_endpoint_injects_auth_and_passes_json_results() -> None:
    server, endpoint_url = _start_fake_sparql_endpoint(
        body={"head": {"vars": ["label"]}, "results": {"bindings": []}},
    )
    endpoint = SparqlEndpoint(
        thing_id="urn:slc:endpoint:energy",
        endpoint_url=endpoint_url,
        security_name="sparql_auth",
        security_definition={"scheme": "bearer"},
        credential=_credential("bearer", {"token": "secret-token"}),
    )
    try:
        response = await query_sparql_endpoint(
            query="SELECT ?label WHERE { ?s ?p ?label }",
            endpoint=endpoint,
            settings=_settings(allow_private=True),
        )
    finally:
        server.shutdown()
        server.server_close()

    assert response["content_type"] == "application/sparql-results+json"
    assert response["results"] == {"head": {"vars": ["label"]}, "results": {"bindings": []}}
    assert _FakeSparqlEndpoint.last_headers["Authorization"] == "Bearer secret-token"
    assert _FakeSparqlEndpoint.last_form == {
        "query": ["SELECT ?label WHERE { ?s ?p ?label }"]
    }


@pytest.mark.anyio
async def test_query_sparql_endpoint_rejects_private_hosts_without_opt_in() -> None:
    endpoint = SparqlEndpoint(
        thing_id="urn:slc:endpoint:energy",
        endpoint_url="http://127.0.0.1:9/sparql",
        security_name=None,
        security_definition={"scheme": "nosec"},
        credential=None,
    )

    with pytest.raises(ValueError, match="private or reserved"):
        await query_sparql_endpoint(
            query="SELECT * WHERE { ?s ?p ?o }",
            endpoint=endpoint,
            settings=_settings(),
        )


@pytest.mark.anyio
async def test_query_sparql_endpoint_enforces_response_size_cap() -> None:
    server, endpoint_url = _start_fake_sparql_endpoint(body={"too": "large"})
    endpoint = SparqlEndpoint(
        thing_id="urn:slc:endpoint:energy",
        endpoint_url=endpoint_url,
        security_name=None,
        security_definition={"scheme": "nosec"},
        credential=None,
    )
    try:
        with pytest.raises(Exception) as exc_info:
            await query_sparql_endpoint(
                query="SELECT * WHERE { ?s ?p ?o }",
                endpoint=endpoint,
                settings=_settings(allow_private=True, max_response_bytes=4),
            )
    finally:
        server.shutdown()
        server.server_close()

    assert getattr(exc_info.value, "status_code", None) == 502
    assert exc_info.value.detail["category"] == "response_size"
