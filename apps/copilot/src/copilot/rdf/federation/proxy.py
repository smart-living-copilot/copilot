"""The credential-injecting SPARQL proxy.

Maps a TD security scheme + stored credential to forwarding auth, then relays the SPARQL
protocol request to the real endpoint with a timeout and a response-size cap. This is the
only component that ever sees the secret or talks to the external endpoint.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from typing import Any

import aiohttp
from fastapi import HTTPException, Request, Response

from copilot.catalog.credentials.models import CredentialRecord
from copilot.rdf.federation._settings import setting_value
from copilot.rdf.federation.endpoints import FederatedEndpoint

_DEFAULT_FEDERATION_USER_AGENT = (
    "SmartLivingCopilot/0.1.0 (https://github.com/Smart-Living-Copilot/copilot; federated-sparql)"
)


def federation_user_agent(settings: Any) -> str:
    value = setting_value(
        settings,
        "RDF_FEDERATION_USER_AGENT",
        "rdf_federation_user_agent",
        default=_DEFAULT_FEDERATION_USER_AGENT,
    )
    user_agent = str(value or "").strip()
    return user_agent or _DEFAULT_FEDERATION_USER_AGENT


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


def build_forwarding_headers(
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
    forward_headers["User-Agent"] = federation_user_agent(settings)
    forward_headers.update(auth_headers)
    return forward_headers


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
    forward_headers = build_forwarding_headers(
        method=request.method,
        request_headers=request.headers,
        auth_headers=auth_headers,
        settings=settings,
    )

    params = list(request.query_params.multi_items())
    params.extend(auth_params)
    body = await request.body() if request.method == "POST" else None
    timeout_seconds = float(
        setting_value(
            settings,
            "RDF_FEDERATION_TIMEOUT_SECONDS",
            "rdf_federation_timeout_seconds",
            default=10,
        )
    )
    max_response_bytes = int(
        setting_value(
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
