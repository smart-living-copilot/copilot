from __future__ import annotations

import base64
import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import aiohttp
from fastapi import HTTPException, Request, Response
from sqlalchemy.orm import Session

from copilot.catalog.credentials.models import CredentialRecord
from copilot.catalog.credentials.store import get_credential
from copilot.catalog.models import Thing

_SERVICE_IRI_RE = re.compile(r"(?is)\bSERVICE\s+(?:SILENT\s+)?<([^>]*)>")
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
_UNSAFE_NETWORK_LABELS = {"localhost"}


@dataclass(frozen=True)
class EndpointMetadata:
    thing_id: str
    endpoint_url: str
    security_name: str | None
    security_definition: dict[str, Any]
    scheme: str


@dataclass(frozen=True)
class FederatedEndpoint:
    thing_id: str
    endpoint_url: str
    security_name: str | None
    security_definition: dict[str, Any]
    credential: CredentialRecord | None


def _setting_value(settings: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(settings, name):
            return getattr(settings, name)
    return default


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


def _mask_sparql_non_code(query: str, *, mask_strings: bool) -> str:
    chars = list(query)
    i = 0
    in_iri = False
    quote: str | None = None
    triple_quote: str | None = None
    escaped = False

    while i < len(chars):
        char = chars[i]
        if quote is not None:
            if mask_strings and char not in {"\n", "\r"}:
                chars[i] = " "
            if escaped:
                escaped = False
                i += 1
                continue
            if char == "\\":
                escaped = True
                i += 1
                continue
            if triple_quote is not None and query.startswith(triple_quote, i):
                if mask_strings:
                    for offset in range(3):
                        chars[i + offset] = " "
                i += 3
                quote = None
                triple_quote = None
                continue
            if triple_quote is None and char == quote:
                quote = None
            i += 1
            continue

        if in_iri:
            if char == ">":
                in_iri = False
            i += 1
            continue

        if char == "<":
            in_iri = True
            i += 1
            continue

        if query.startswith('"""', i) or query.startswith("'''", i):
            triple_quote = query[i : i + 3]
            quote = query[i]
            if mask_strings:
                for offset in range(3):
                    chars[i + offset] = " "
            i += 3
            continue

        if char in {'"', "'"}:
            quote = char
            if mask_strings:
                chars[i] = " "
            i += 1
            continue

        if char == "#":
            while i < len(chars) and chars[i] not in {"\n", "\r"}:
                chars[i] = " "
                i += 1
            continue

        i += 1

    return "".join(chars)


def strip_sparql_comments(query: str) -> str:
    """Replace SPARQL comments with spaces while preserving string/IRI content."""
    return _mask_sparql_non_code(query, mask_strings=False)


def _mask_sparql_strings_and_comments(query: str) -> str:
    return _mask_sparql_non_code(query, mask_strings=True)


def service_iris(query: str) -> list[str]:
    stripped = _mask_sparql_strings_and_comments(query)
    return [match.group(1) for match in _SERVICE_IRI_RE.finditer(stripped)]


def rewrite_federated_query(query: str, service_rewrites: dict[str, str] | None = None) -> str:
    rewrites = service_rewrites or {}
    stripped = _mask_sparql_strings_and_comments(query)
    pieces: list[str] = []
    last = 0
    for match in _SERVICE_IRI_RE.finditer(stripped):
        iri = match.group(1)
        replacement = rewrites.get(iri)
        if not replacement:
            raise ValueError(
                "SPARQL SERVICE targets must be declared endpoint Thing ids passed in endpoints"
            )
        pieces.append(query[last : match.start(1)])
        pieces.append(replacement)
        last = match.end(1)

    if not pieces:
        return query
    pieces.append(query[last:])
    return "".join(pieces)


def endpoint_proxy_url(base_url: str, thing_id: str) -> str:
    return f"{base_url.rstrip('/')}/rdf/federate/{quote(thing_id, safe='')}/sparql"


def thing_id_from_proxy_path(encoded_thing_id_path: str) -> str:
    suffix = "/sparql"
    if not encoded_thing_id_path.endswith(suffix):
        raise HTTPException(status_code=404, detail="Federated SPARQL endpoint not found")
    encoded_thing_id = encoded_thing_id_path[: -len(suffix)]
    if not encoded_thing_id:
        raise HTTPException(status_code=404, detail="Federated SPARQL endpoint not found")
    return unquote(encoded_thing_id)


def _allowed_host_entries(settings: Any) -> set[str]:
    raw = _setting_value(
        settings,
        "RDF_FEDERATION_ALLOWED_HOSTS",
        "rdf_federation_allowed_hosts",
        default="",
    )
    if isinstance(raw, str):
        return {item.strip().lower() for item in raw.split(",") if item.strip()}
    if isinstance(raw, list | tuple | set):
        return {str(item).strip().lower() for item in raw if str(item).strip()}
    return set()


def _host_is_allowlisted(host: str, port: int | None, allowed_hosts: set[str]) -> bool:
    normalized_host = host.lower().rstrip(".")
    candidates = {normalized_host}
    if port is not None:
        candidates.add(f"{normalized_host}:{port}")
    for allowed in allowed_hosts:
        normalized_allowed = allowed.lower().rstrip(".")
        if normalized_allowed == "*" or normalized_allowed in candidates:
            return True
        if normalized_allowed.startswith("*.") and normalized_host.endswith(
            normalized_allowed[1:]
        ):
            return True
    return False


def _resolve_host_addresses(host: str) -> list[ipaddress._BaseAddress]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass

    addresses: list[ipaddress._BaseAddress] = []
    try:
        results = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Federated endpoint host could not be resolved: {host}") from exc
    for result in results:
        raw_address = result[4][0]
        try:
            addresses.append(ipaddress.ip_address(raw_address))
        except ValueError:
            continue
    if not addresses:
        raise ValueError(f"Federated endpoint host could not be resolved: {host}")
    return addresses


def _address_is_private_or_reserved(address: ipaddress._BaseAddress) -> bool:
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )


def validate_endpoint_url(endpoint_url: str, settings: Any) -> None:
    parsed = urlsplit(endpoint_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Federated SPARQL endpoints must use http or https")
    if not parsed.hostname:
        raise ValueError("Federated SPARQL endpoint URL must include a host")
    if parsed.username or parsed.password:
        raise ValueError("Federated SPARQL endpoint URL must not include credentials")

    allowed_hosts = _allowed_host_entries(settings)
    if _host_is_allowlisted(parsed.hostname, parsed.port, allowed_hosts):
        return

    allow_private = bool(
        _setting_value(
            settings,
            "RDF_FEDERATION_ALLOW_PRIVATE_ENDPOINTS",
            "rdf_federation_allow_private_endpoints",
            default=False,
        )
    )
    if allow_private:
        return

    if parsed.hostname.lower().rstrip(".") in _UNSAFE_NETWORK_LABELS:
        raise ValueError("Federated SPARQL endpoint host is private or reserved")

    for address in _resolve_host_addresses(parsed.hostname):
        if _address_is_private_or_reserved(address):
            raise ValueError("Federated SPARQL endpoint host resolves to private or reserved IPs")


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
        raise ValueError("Federated endpoint Thing must declare @type sd:Service")

    supported_languages = set(_document_id_values(document, _SD_SUPPORTED_LANGUAGE_KEYS))
    if supported_languages and not supported_languages.intersection(_SPARQL_11_QUERY_TYPES):
        raise ValueError("Federated endpoint Thing must support sd:SPARQL11Query")
    if not supported_languages:
        raise ValueError("Federated endpoint Thing must declare sd:supportedLanguage")

    endpoint_url = _first_id_value(_document_value(document, _SD_ENDPOINT_KEYS))
    if endpoint_url is None:
        raise ValueError("Federated endpoint Thing must declare sd:endpoint")
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
        raise ValueError(
            f"Federated endpoint Thing is missing securityDefinitions.{security_name}"
        )

    scheme = str(security_definition.get("scheme") or "").strip().lower()
    if not scheme:
        raise ValueError("Federated endpoint security definition must declare a scheme")

    return EndpointMetadata(
        thing_id=thing_id,
        endpoint_url=endpoint_url,
        security_name=security_name,
        security_definition=security_definition,
        scheme=scheme,
    )


def resolve_federated_endpoint(
    session: Session,
    *,
    thing_id: str,
    settings: Any,
) -> FederatedEndpoint:
    thing = session.get(Thing, thing_id)
    if thing is None:
        raise ValueError(f"Federated endpoint Thing not found: {thing_id}")

    metadata = endpoint_metadata_from_document(
        thing_id=thing_id,
        document=thing.document,
        settings=settings,
    )
    credential = None
    if metadata.scheme != "nosec":
        if metadata.security_name is None:
            raise ValueError("Federated endpoint credential requires a security name")
        credential = get_credential(session, thing_id, metadata.security_name)
        if credential is None:
            raise ValueError(
                f"Federated endpoint credential not found: {thing_id}#{metadata.security_name}"
            )
        if credential.scheme.strip().lower() != metadata.scheme:
            raise ValueError("Federated endpoint credential scheme does not match the TD")

    return FederatedEndpoint(
        thing_id=thing_id,
        endpoint_url=metadata.endpoint_url,
        security_name=metadata.security_name,
        security_definition=metadata.security_definition,
        credential=credential,
    )


def _secret_value(credentials: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = credentials.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def build_forwarding_auth(
    *,
    security_definition: dict[str, Any],
    credential: CredentialRecord | None,
) -> tuple[dict[str, str], list[tuple[str, str]]]:
    scheme = str(security_definition.get("scheme") or "").strip().lower()
    if scheme == "nosec":
        return {}, []
    if credential is None:
        raise ValueError("Federated endpoint credential is required")

    credentials = dict(credential.credentials or {})
    if scheme == "bearer":
        token = _secret_value(
            credentials,
            "token",
            "access_token",
            "accessToken",
            "bearer_token",
            "bearerToken",
            "api_key",
            "key",
        )
        if token is None:
            raise ValueError("Bearer credential must include a token")
        return {"Authorization": f"Bearer {token}"}, []

    if scheme == "basic":
        username = _secret_value(credentials, "username", "user")
        password = _secret_value(credentials, "password", "pass")
        if username is None or password is None:
            raise ValueError("Basic credential must include username and password")
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}, []

    if scheme in {"apikey", "apiKey"}:
        name = security_definition.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("API key security definition must include a name")
        value = _secret_value(credentials, name, "value", "api_key", "apiKey", "key", "token")
        if value is None:
            raise ValueError("API key credential must include a value")
        location = str(security_definition.get("in") or "header").strip().lower()
        if location == "header":
            return {name: value}, []
        if location == "query":
            return {}, [(name, value)]
        if location == "cookie":
            return {"Cookie": f"{name}={value}"}, []
        raise ValueError("API key security definition must use header, query, or cookie")

    raise ValueError(f"Unsupported federated endpoint security scheme: {scheme}")


async def proxy_sparql_request(
    request: Request,
    *,
    endpoint: FederatedEndpoint,
    settings: Any,
) -> Response:
    auth_headers, auth_params = build_forwarding_auth(
        security_definition=endpoint.security_definition,
        credential=endpoint.credential,
    )
    forward_headers: dict[str, str] = {}
    accept = request.headers.get("accept")
    if accept:
        forward_headers["Accept"] = accept
    content_type = request.headers.get("content-type")
    if request.method == "POST" and content_type:
        forward_headers["Content-Type"] = content_type
    forward_headers.update(auth_headers)

    params = list(request.query_params.multi_items())
    params.extend(auth_params)
    body = await request.body() if request.method == "POST" else None
    timeout_seconds = float(
        _setting_value(
            settings,
            "RDF_FEDERATION_TIMEOUT_SECONDS",
            "rdf_federation_timeout_seconds",
            default=10,
        )
    )
    max_response_bytes = int(
        _setting_value(
            settings,
            "RDF_FEDERATION_MAX_RESPONSE_BYTES",
            "rdf_federation_max_response_bytes",
            default=2_000_000,
        )
    )

    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout_seconds)
        ) as session:
            async with session.request(
                request.method,
                endpoint.endpoint_url,
                params=params,
                data=body,
                headers=forward_headers,
            ) as upstream:
                chunks = bytearray()
                async for chunk in upstream.content.iter_chunked(65536):
                    chunks.extend(chunk)
                    if len(chunks) > max_response_bytes:
                        raise HTTPException(
                            status_code=502,
                            detail="Federated SPARQL response exceeded the size limit",
                        )
                content_type = upstream.headers.get("content-type")
                return Response(
                    content=bytes(chunks),
                    status_code=upstream.status,
                    media_type=content_type.split(";", 1)[0] if content_type else None,
                )
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Federated SPARQL endpoint timed out") from exc
    except aiohttp.ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
