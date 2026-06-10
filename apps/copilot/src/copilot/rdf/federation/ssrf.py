"""SSRF containment for federated endpoint URLs.

`validate_endpoint_url` is the gate that keeps the proxy from being pointed at internal
hosts: scheme/host checks, an explicit allowlist, and a private/reserved-IP rejection.
Note the validate-vs-use DNS gap (resolution happens here, the request re-resolves later)
— see the DNS-rebinding item in the federation roadmap.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlsplit

from copilot.rdf.federation._settings import setting_value

_UNSAFE_NETWORK_LABELS = {"localhost"}


def _allowed_host_entries(settings: Any) -> set[str]:
    raw = setting_value(
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
        if normalized_allowed.startswith("*.") and normalized_host.endswith(normalized_allowed[1:]):
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
        setting_value(
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
