"""SSRF containment for external endpoint URLs.

`resolve_endpoint_url` is the gate that keeps direct endpoint requests from being pointed
at internal hosts: scheme/host checks, an explicit allowlist, private/reserved-IP
rejection, and the resolved addresses that callers can pin for the subsequent request.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from copilot.rdf.endpoint_client._settings import setting_value

_UNSAFE_NETWORK_LABELS = {"localhost"}


@dataclass(frozen=True)
class ResolvedEndpointUrl:
    hostname: str
    port: int
    addresses: tuple[str, ...]


def _allowed_host_entries(settings: Any) -> set[str]:
    raw = setting_value(
        settings,
        "RDF_ENDPOINT_ALLOWED_HOSTS",
        "rdf_endpoint_allowed_hosts",
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


def _resolve_host_addresses(host: str, port: int) -> list[ipaddress._BaseAddress]:
    try:
        return [ipaddress.ip_address(host)]
    except ValueError:
        pass

    addresses: list[ipaddress._BaseAddress] = []
    try:
        results = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"SPARQL endpoint host could not be resolved: {host}") from exc
    for result in results:
        raw_address = result[4][0]
        try:
            addresses.append(ipaddress.ip_address(raw_address))
        except ValueError:
            continue
    if not addresses:
        raise ValueError(f"SPARQL endpoint host could not be resolved: {host}")
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


def resolve_endpoint_url(endpoint_url: str, settings: Any) -> ResolvedEndpointUrl:
    parsed = urlsplit(endpoint_url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("SPARQL endpoints must use http or https")
    if not parsed.hostname:
        raise ValueError("SPARQL endpoint URL must include a host")
    if parsed.username or parsed.password:
        raise ValueError("SPARQL endpoint URL must not include credentials")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    addresses = _resolve_host_addresses(parsed.hostname, port)

    allowed_hosts = _allowed_host_entries(settings)
    if _host_is_allowlisted(parsed.hostname, parsed.port, allowed_hosts):
        return ResolvedEndpointUrl(
            hostname=parsed.hostname,
            port=port,
            addresses=tuple(str(address) for address in addresses),
        )

    allow_private = bool(
        setting_value(
            settings,
            "RDF_ENDPOINT_ALLOW_PRIVATE",
            "rdf_endpoint_allow_private",
            default=False,
        )
    )
    if allow_private:
        return ResolvedEndpointUrl(
            hostname=parsed.hostname,
            port=port,
            addresses=tuple(str(address) for address in addresses),
        )

    if parsed.hostname.lower().rstrip(".") in _UNSAFE_NETWORK_LABELS:
        raise ValueError("SPARQL endpoint host is private or reserved")

    for address in addresses:
        if _address_is_private_or_reserved(address):
            raise ValueError("SPARQL endpoint host resolves to private or reserved IPs")

    return ResolvedEndpointUrl(
        hostname=parsed.hostname,
        port=port,
        addresses=tuple(str(address) for address in addresses),
    )


def validate_endpoint_url(endpoint_url: str, settings: Any) -> None:
    resolve_endpoint_url(endpoint_url, settings)
