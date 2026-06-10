"""Federated SPARQL.

Split into focused submodules:
- `sparql_text` — comment/string masking, SERVICE rewriting, join diagnostics
- `ssrf`       — endpoint-URL validation / SSRF containment
- `endpoints`  — endpoint-Thing metadata, resolution, proxy-path mapping
- `proxy`      — credential injection + the forwarding SPARQL proxy

This package re-exports the public API so existing `copilot.rdf.federation` imports work.
"""

from __future__ import annotations

from copilot.rdf.federation.endpoints import (
    EndpointMetadata,
    FederatedEndpoint,
    endpoint_metadata_from_document,
    endpoint_proxy_url,
    resolve_federated_endpoint,
    thing_id_from_proxy_path,
)
from copilot.rdf.federation.proxy import (
    build_forwarding_auth,
    build_forwarding_headers,
    federation_user_agent,
    proxy_sparql_request,
)
from copilot.rdf.federation.sparql_text import (
    rewrite_federated_query,
    service_constraint_diagnostics,
    service_iris,
    strip_sparql_comments,
)
from copilot.rdf.federation.ssrf import validate_endpoint_url

__all__ = [
    "EndpointMetadata",
    "FederatedEndpoint",
    "build_forwarding_auth",
    "build_forwarding_headers",
    "endpoint_metadata_from_document",
    "endpoint_proxy_url",
    "federation_user_agent",
    "proxy_sparql_request",
    "resolve_federated_endpoint",
    "rewrite_federated_query",
    "service_constraint_diagnostics",
    "service_iris",
    "strip_sparql_comments",
    "thing_id_from_proxy_path",
    "validate_endpoint_url",
]
