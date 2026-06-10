"""Credential-injecting direct SPARQL endpoint client."""

from __future__ import annotations

import base64
import ipaddress
import json
import socket
from collections.abc import Mapping
from typing import Any

import aiohttp
from aiohttp.abc import AbstractResolver
from fastapi import HTTPException

from copilot.catalog.credentials.models import CredentialRecord
from copilot.rdf.endpoint_client._settings import setting_value
from copilot.rdf.endpoint_client.endpoints import SparqlEndpoint
from copilot.rdf.endpoint_client.ssrf import ResolvedEndpointUrl, resolve_endpoint_url

_DEFAULT_ENDPOINT_USER_AGENT = (
    "SmartLivingCopilot/0.1.0 (https://github.com/Smart-Living-Copilot/copilot; sparql-endpoint)"
)


def endpoint_user_agent(settings: Any) -> str:
    value = setting_value(
        settings,
        "RDF_ENDPOINT_USER_AGENT",
        "rdf_endpoint_user_agent",
        default=_DEFAULT_ENDPOINT_USER_AGENT,
    )
    user_agent = str(value or "").strip()
    return user_agent or _DEFAULT_ENDPOINT_USER_AGENT


def _secret_value(credentials: dict[str, Any], *names: str) -> str | None:
    for name in names:
        value = credentials.get(name)
        if isinstance(value, str) and value:
            return value
    return None


def build_endpoint_auth(
    *,
    security_definition: dict[str, Any],
    credential: CredentialRecord | None,
) -> tuple[dict[str, str], list[tuple[str, str]]]:
    scheme = str(security_definition.get("scheme") or "").strip().lower()
    if scheme == "nosec":
        return {}, []
    if credential is None:
        raise ValueError("SPARQL endpoint credential is required")

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

    raise ValueError(f"Unsupported SPARQL endpoint security scheme: {scheme}")


def build_endpoint_headers(
    *,
    method: str,
    request_headers: Mapping[str, str],
    auth_headers: dict[str, str],
    settings: Any,
) -> dict[str, str]:
    forward_headers: dict[str, str] = {}
    accept = request_headers.get("accept")
    if accept:
        forward_headers["Accept"] = accept
    content_type = request_headers.get("content-type")
    if method == "POST" and content_type:
        forward_headers["Content-Type"] = content_type
    forward_headers["User-Agent"] = endpoint_user_agent(settings)
    forward_headers.update(auth_headers)
    return forward_headers


class _PinnedResolver(AbstractResolver):
    def __init__(self, resolved: ResolvedEndpointUrl) -> None:
        self._resolved = resolved

    async def resolve(
        self,
        host: str,
        port: int = 0,
        family: socket.AddressFamily = socket.AF_INET,
    ) -> list[dict[str, Any]]:
        if host.lower().rstrip(".") != self._resolved.hostname.lower().rstrip("."):
            raise OSError("Unexpected endpoint host during pinned resolution")

        resolved_port = port or self._resolved.port
        results: list[dict[str, Any]] = []
        for address in self._resolved.addresses:
            parsed = ipaddress.ip_address(address)
            address_family = socket.AF_INET6 if parsed.version == 6 else socket.AF_INET
            if family not in {socket.AF_UNSPEC, address_family}:
                continue
            results.append(
                {
                    "hostname": host,
                    "host": address,
                    "port": resolved_port,
                    "family": address_family,
                    "proto": socket.IPPROTO_TCP,
                    "flags": 0,
                }
            )
        if not results:
            raise OSError("No pinned endpoint addresses match the requested address family")
        return results

    async def close(self) -> None:
        return None


def _endpoint_error_detail(
    *,
    category: str,
    message: str,
    retryable: bool,
) -> dict[str, Any]:
    return {
        "category": category,
        "message": message,
        "retryable": retryable,
    }


def _upstream_error_detail(status: int, body: str) -> dict[str, Any]:
    message = body.strip() or f"SPARQL endpoint returned status {status}"
    if status in {401, 403}:
        return _endpoint_error_detail(
            category="auth",
            message=message,
            retryable=False,
        )
    return _endpoint_error_detail(
        category="endpoint",
        message=message,
        retryable=status in {400, 408, 409, 429, 500, 502, 503, 504},
    )


def _endpoint_timeout_seconds(settings: Any) -> float:
    return float(
        setting_value(
            settings,
            "RDF_ENDPOINT_TIMEOUT_SECONDS",
            "rdf_endpoint_timeout_seconds",
            default=10,
        )
    )


def _endpoint_max_response_bytes(settings: Any) -> int:
    return int(
        setting_value(
            settings,
            "RDF_ENDPOINT_MAX_RESPONSE_BYTES",
            "rdf_endpoint_max_response_bytes",
            default=2_000_000,
        )
    )


async def query_sparql_endpoint(
    *,
    query: str,
    endpoint: SparqlEndpoint,
    settings: Any,
) -> dict[str, Any]:
    resolved = resolve_endpoint_url(endpoint.endpoint_url, settings)
    auth_headers, auth_params = build_endpoint_auth(
        security_definition=endpoint.security_definition,
        credential=endpoint.credential,
    )
    headers = build_endpoint_headers(
        method="POST",
        request_headers={
            "accept": "application/sparql-results+json, application/json;q=0.9",
            "content-type": "application/x-www-form-urlencoded",
        },
        auth_headers=auth_headers,
        settings=settings,
    )
    connector = aiohttp.TCPConnector(resolver=_PinnedResolver(resolved))

    try:
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=_endpoint_timeout_seconds(settings)),
        ) as session:
            async with session.post(
                endpoint.endpoint_url,
                params=auth_params,
                data={"query": query},
                headers=headers,
            ) as upstream:
                chunks = bytearray()
                async for chunk in upstream.content.iter_chunked(65536):
                    chunks.extend(chunk)
                    if len(chunks) > _endpoint_max_response_bytes(settings):
                        raise HTTPException(
                            status_code=502,
                            detail=_endpoint_error_detail(
                                category="response_size",
                                message="SPARQL endpoint response exceeded the size limit",
                                retryable=True,
                            ),
                        )

                content_type = upstream.headers.get("content-type")
                body = bytes(chunks).decode(upstream.charset or "utf-8", errors="replace")
                if upstream.status >= 400:
                    raise HTTPException(
                        status_code=upstream.status,
                        detail=_upstream_error_detail(upstream.status, body),
                    )

                try:
                    results = json.loads(body)
                except json.JSONDecodeError as exc:
                    raise HTTPException(
                        status_code=502,
                        detail=_endpoint_error_detail(
                            category="endpoint",
                            message="SPARQL endpoint returned non-JSON results",
                            retryable=True,
                        ),
                    ) from exc
                if not isinstance(results, dict):
                    raise HTTPException(
                        status_code=502,
                        detail=_endpoint_error_detail(
                            category="endpoint",
                            message="SPARQL endpoint returned a non-object JSON result",
                            retryable=True,
                        ),
                    )

                return {
                    "endpoint_url": endpoint.endpoint_url,
                    "content_type": content_type.split(";", 1)[0] if content_type else None,
                    "results": results,
                }
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=_endpoint_error_detail(
                category="timeout",
                message="SPARQL endpoint timed out",
                retryable=True,
            ),
        ) from exc
    except aiohttp.ClientError as exc:
        raise HTTPException(
            status_code=502,
            detail=_endpoint_error_detail(
                category="endpoint",
                message=str(exc),
                retryable=True,
            ),
        ) from exc
