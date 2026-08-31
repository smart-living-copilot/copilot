"""Turning one URL a person pasted into a registered discovery source.

The registry decides which providers probe and in what order: every provider
declaring the ``detect`` capability is tried, most specific first. Nothing here
knows the name of any provider.
"""

from __future__ import annotations

import aiohttp

from wotbot.discovery.detection import DetectionContext, origin
from wotbot.discovery.errors import ProviderError
from wotbot.discovery.http import BoundedHttpClient
from wotbot.discovery.models import SourceDefinition
from wotbot.discovery.providers.base import DiscoveryProvider
from wotbot.discovery.providers.toolhive import detect_toolhive


def detectors(registry: dict[str, DiscoveryProvider]) -> list[DiscoveryProvider]:
    """Return the detecting providers, most specific probe first."""

    return sorted(
        (provider for provider in registry.values() if "detect" in provider.capabilities),
        key=lambda provider: (provider.detect_priority, provider.name),
    )


async def resolve_public_source(
    url: str,
) -> tuple[SourceDefinition | None, list[str], bool]:
    """Probe a public URL against every detecting provider."""

    from wotbot.discovery.providers import PROVIDERS

    context = DetectionContext(
        url=url,
        # One budget for the whole detection, shared by every probe, so a long
        # provider list cannot multiply requests against a stranger's server.
        http=BoundedHttpClient(mode="public", max_requests=12, max_bytes=4 * 1024 * 1024),
    )
    for provider in detectors(PROVIDERS):
        try:
            source = await provider.inspect_public(context)
        except (aiohttp.ClientError, OSError, TimeoutError, ProviderError) as exc:
            context.note(f"{provider.name} probe failed: {exc}")
            continue
        if source is not None:
            return source, context.evidence, True
    return None, context.evidence, False


async def resolve_private_toolhive_source(
    url: str,
) -> tuple[SourceDefinition | None, list[str], bool]:
    """Probe a private URL for ToolHive only.

    A private address is exempt from the public address policy, so it is
    reached deliberately and never by the open detection chain.
    """

    evidence: list[str] = []
    source = await detect_toolhive(origin(url), public_http=None, notes=evidence.append)
    return source, evidence, source is not None
