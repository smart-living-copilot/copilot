from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from copilot.catalog.credentials.models import CredentialRecord
from copilot.rdf.federation import (
    build_forwarding_auth,
    build_forwarding_headers,
    endpoint_metadata_from_document,
    endpoint_proxy_url,
    federation_user_agent,
    rewrite_federated_query,
    service_constraint_diagnostics,
    service_iris,
    thing_id_from_proxy_path,
)


class Settings:
    RDF_FEDERATION_ALLOWED_HOSTS = ""
    RDF_FEDERATION_ALLOW_PRIVATE_ENDPOINTS = False


def _settings(**values):
    return SimpleNamespace(
        RDF_FEDERATION_ALLOWED_HOSTS=values.get("allowed_hosts", ""),
        RDF_FEDERATION_ALLOW_PRIVATE_ENDPOINTS=values.get("allow_private", False),
        RDF_FEDERATION_USER_AGENT=values.get("user_agent", ""),
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


def test_rewrite_federated_query_replaces_endpoint_ids_and_preserves_silent():
    query = """
        SELECT ?x WHERE {
            SERVICE SILENT <urn:slc:endpoint:energy> { ?x ?p ?o }
        }
    """

    rewritten = rewrite_federated_query(
        query,
        {"urn:slc:endpoint:energy": "http://localhost:8124/rdf/federate/x/sparql"},
    )

    assert "SERVICE SILENT <http://localhost:8124/rdf/federate/x/sparql>" in rewritten


def test_rewrite_federated_query_rejects_undeclared_service_targets():
    with pytest.raises(ValueError, match="endpoint Thing ids"):
        rewrite_federated_query(
            "SELECT * WHERE { SERVICE <https://example.com/sparql> { ?s ?p ?o } }",
            {},
        )


def test_service_iris_ignores_comments_strings_and_hash_iris():
    query = """
        PREFIX brick: <https://brickschema.org/schema/Brick#>
        # SERVICE <https://example.com/commented> { ?s ?p ?o }
        SELECT * WHERE {
            BIND("# not a comment" AS ?label)
            BIND("SERVICE <https://example.com/string> { ?s ?p ?o }" AS ?debug)
            SERVICE <urn:slc:endpoint:energy> { ?s ?p ?o }
        }
    """

    assert service_iris(query) == ["urn:slc:endpoint:energy"]


def test_service_constraint_diagnostics_warns_for_unbounded_join():
    query = """
        SELECT ?thing ?remote WHERE {
            ?thing <https://example.com/externalId> ?externalId .
            SERVICE <urn:slc:endpoint:energy> {
                ?externalId <https://example.com/remoteValue> ?remote .
            }
        }
    """

    diagnostics = service_constraint_diagnostics(query)

    assert diagnostics == [
        {
            "code": "service-unbounded-join",
            "service_iri": "urn:slc:endpoint:energy",
            "message": (
                "SERVICE block shares variables with outer graph patterns but has no "
                "inner VALUES, FILTER, or BIND constraint; outer bindings are not "
                "pushed into SERVICE."
            ),
        }
    ]


def test_service_constraint_diagnostics_accepts_inner_values_constraint():
    query = """
        SELECT ?thing ?remote WHERE {
            ?thing <https://example.com/externalId> ?externalId .
            SERVICE <urn:slc:endpoint:energy> {
                VALUES ?externalId { "meter-1" "meter-2" }
                ?externalId <https://example.com/remoteValue> ?remote .
            }
        }
    """

    assert service_constraint_diagnostics(query) == []


def test_service_constraint_diagnostics_ignores_external_only_service_query():
    query = """
        SELECT ?remote WHERE {
            SERVICE <urn:slc:endpoint:energy> {
                ?sensor <https://example.com/remoteValue> ?remote .
            }
        }
    """

    assert service_constraint_diagnostics(query) == []


def test_service_constraint_diagnostics_ignores_comments_and_strings():
    query = """
        SELECT ?thing ?remote WHERE {
            ?thing <https://example.com/externalId> ?externalId .
            SERVICE <urn:slc:endpoint:energy> {
                # FILTER(?externalId = "meter-1")
                ?externalId <https://example.com/debug> "VALUES ?externalId { 'meter-1' }" .
                ?externalId <https://example.com/remoteValue> ?remote .
            }
        }
    """

    assert [diagnostic["code"] for diagnostic in service_constraint_diagnostics(query)] == [
        "service-unbounded-join"
    ]


def test_endpoint_proxy_url_urlencodes_thing_ids():
    assert (
        endpoint_proxy_url("http://localhost:8124/", "urn:slc:endpoint:energy/kg")
        == "http://localhost:8124/rdf/federate/urn%3Aslc%3Aendpoint%3Aenergy%2Fkg/sparql"
    )
    assert thing_id_from_proxy_path("urn%3Aslc%3Aendpoint%3Aenergy%2Fkg/sparql") == (
        "urn:slc:endpoint:energy/kg"
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


def test_build_forwarding_auth_supports_bearer_basic_and_api_key():
    bearer_headers, bearer_params = build_forwarding_auth(
        security_definition={"scheme": "bearer"},
        credential=_credential("bearer", {"token": "secret-token"}),
    )
    assert bearer_headers == {"Authorization": "Bearer secret-token"}
    assert bearer_params == []

    basic_headers, basic_params = build_forwarding_auth(
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

    api_key_headers, api_key_params = build_forwarding_auth(
        security_definition={"scheme": "apikey", "in": "header", "name": "X-API-Key"},
        credential=_credential("apikey", {"value": "key-1"}),
    )
    assert api_key_headers == {"X-API-Key": "key-1"}
    assert api_key_params == []

    query_headers, query_params = build_forwarding_auth(
        security_definition={"scheme": "apikey", "in": "query", "name": "api_key"},
        credential=_credential("apikey", {"api_key": "key-2"}),
    )
    assert query_headers == {}
    assert query_params == [("api_key", "key-2")]


def test_build_forwarding_auth_allows_nosec_without_credentials():
    headers, params = build_forwarding_auth(
        security_definition={"scheme": "nosec"},
        credential=None,
    )

    assert headers == {}
    assert params == []


def test_federation_user_agent_uses_default_when_setting_is_blank():
    assert federation_user_agent(_settings(user_agent="")).startswith("SmartLivingCopilot/")


def test_build_forwarding_headers_sends_configured_user_agent():
    headers = build_forwarding_headers(
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
