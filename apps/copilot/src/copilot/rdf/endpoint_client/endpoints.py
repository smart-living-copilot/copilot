"""Endpoint-Thing metadata and credential resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from copilot.catalog.credentials.models import CredentialRecord
from copilot.catalog.credentials.store import get_credential
from copilot.catalog.models import Thing
from copilot.rdf.endpoint_client.ssrf import validate_endpoint_url

_SD_SERVICE_TYPES = {
    "sd:Service",
    "http://www.w3.org/ns/sparql-service-description#Service",
    "https://www.w3.org/ns/sparql-service-description#Service",
}
_SPARQL_11_QUERY_TYPES = {
    "sd:SPARQL11Query",
    "http://www.w3.org/ns/sparql-service-description#SPARQL11Query",
    "https://www.w3.org/ns/sparql-service-description#SPARQL11Query",
}
_SD_ENDPOINT_KEYS = (
    "sd:endpoint",
    "endpoint",
    "http://www.w3.org/ns/sparql-service-description#endpoint",
    "https://www.w3.org/ns/sparql-service-description#endpoint",
)
_SD_SUPPORTED_LANGUAGE_KEYS = (
    "sd:supportedLanguage",
    "supportedLanguage",
    "http://www.w3.org/ns/sparql-service-description#supportedLanguage",
    "https://www.w3.org/ns/sparql-service-description#supportedLanguage",
)


@dataclass(frozen=True)
class EndpointMetadata:
    thing_id: str
    endpoint_url: str
    security_name: str | None
    security_definition: dict[str, Any]
    scheme: str


@dataclass(frozen=True)
class SparqlEndpoint:
    thing_id: str
    endpoint_url: str
    security_name: str | None
    security_definition: dict[str, Any]
    credential: CredentialRecord | None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _id_value(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        candidate = value.get("@id") or value.get("id")
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _first_id_value(value: Any) -> str | None:
    for item in _as_list(value):
        candidate = _id_value(item)
        if candidate:
            return candidate
    return None


def _document_value(document: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in document:
            return document[key]
    return None


def _document_id_values(document: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    value = _document_value(document, keys)
    values: list[str] = []
    for item in _as_list(value):
        candidate = _id_value(item)
        if candidate:
            values.append(candidate)
    return values


def endpoint_metadata_from_document(
    *,
    thing_id: str,
    document: dict[str, Any],
    settings: Any,
) -> EndpointMetadata:
    type_values = {
        candidate
        for value in _as_list(document.get("@type") or document.get("type"))
        if (candidate := _id_value(value))
    }
    if not type_values.intersection(_SD_SERVICE_TYPES):
        raise ValueError("SPARQL endpoint Thing must declare @type sd:Service")

    supported_languages = set(_document_id_values(document, _SD_SUPPORTED_LANGUAGE_KEYS))
    if supported_languages and not supported_languages.intersection(_SPARQL_11_QUERY_TYPES):
        raise ValueError("SPARQL endpoint Thing must support sd:SPARQL11Query")
    if not supported_languages:
        raise ValueError("SPARQL endpoint Thing must declare sd:supportedLanguage")

    endpoint_url = _first_id_value(_document_value(document, _SD_ENDPOINT_KEYS))
    if endpoint_url is None:
        raise ValueError("SPARQL endpoint Thing must declare sd:endpoint")
    validate_endpoint_url(endpoint_url, settings)

    security_name = _first_id_value(document.get("security"))
    security_definitions = document.get("securityDefinitions")
    if security_name is None:
        security_definition: dict[str, Any] = {"scheme": "nosec"}
    elif isinstance(security_definitions, dict) and isinstance(
        security_definitions.get(security_name),
        dict,
    ):
        security_definition = dict(security_definitions[security_name])
    else:
        raise ValueError(f"SPARQL endpoint Thing is missing securityDefinitions.{security_name}")

    scheme = str(security_definition.get("scheme") or "").strip().lower()
    if not scheme:
        raise ValueError("SPARQL endpoint security definition must declare a scheme")

    return EndpointMetadata(
        thing_id=thing_id,
        endpoint_url=endpoint_url,
        security_name=security_name,
        security_definition=security_definition,
        scheme=scheme,
    )


def resolve_sparql_endpoint(
    session: Session,
    *,
    thing_id: str,
    settings: Any,
) -> SparqlEndpoint:
    thing = session.get(Thing, thing_id)
    if thing is None:
        raise ValueError(f"SPARQL endpoint Thing not found: {thing_id}")

    metadata = endpoint_metadata_from_document(
        thing_id=thing_id,
        document=thing.document,
        settings=settings,
    )
    credential = None
    if metadata.scheme != "nosec":
        if metadata.security_name is None:
            raise ValueError("SPARQL endpoint credential requires a security name")
        credential = get_credential(session, thing_id, metadata.security_name)
        if credential is None:
            raise ValueError(
                f"SPARQL endpoint credential not found: {thing_id}#{metadata.security_name}"
            )
        if credential.scheme.strip().lower() != metadata.scheme:
            raise ValueError("SPARQL endpoint credential scheme does not match the TD")

    return SparqlEndpoint(
        thing_id=thing_id,
        endpoint_url=metadata.endpoint_url,
        security_name=metadata.security_name,
        security_definition=metadata.security_definition,
        credential=credential,
    )
