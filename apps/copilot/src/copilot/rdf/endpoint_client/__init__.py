"""External SPARQL endpoint helpers.

Split into focused submodules:
- `ssrf`       — endpoint-URL validation / SSRF containment
- `endpoints`  — endpoint-Thing metadata and credential resolution
- `client`     — credential injection + direct SPARQL endpoint calls
"""

from __future__ import annotations

from copilot.rdf.endpoint_client.endpoints import (
    EndpointMetadata,
    SparqlEndpoint,
    endpoint_metadata_from_document,
    resolve_sparql_endpoint,
)
from copilot.rdf.endpoint_client.client import (
    build_endpoint_auth,
    build_endpoint_headers,
    endpoint_user_agent,
    query_sparql_endpoint,
)
from copilot.rdf.endpoint_client.ssrf import (
    ResolvedEndpointUrl,
    resolve_endpoint_url,
    validate_endpoint_url,
)

__all__ = [
    "EndpointMetadata",
    "ResolvedEndpointUrl",
    "SparqlEndpoint",
    "build_endpoint_auth",
    "build_endpoint_headers",
    "endpoint_metadata_from_document",
    "endpoint_user_agent",
    "query_sparql_endpoint",
    "resolve_endpoint_url",
    "resolve_sparql_endpoint",
    "validate_endpoint_url",
]
