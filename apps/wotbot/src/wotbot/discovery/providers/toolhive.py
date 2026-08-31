"""ToolHive: MCP servers a ToolHive registry is currently running.

Expects a ToolHive control API answering ``GET {url}/api/v1beta/workloads``
with a JSON list, or an object wrapping one under ``data``, ``items``, or
``workloads``. Each workload needs a ``name`` (or ``id``), a ``status``, and a
``url`` (or ``endpoint``). Only workloads reporting ``running`` are offered.

Configuration
    ``url``
        The ToolHive control API. Required.
    ``reported_host``
        The host ToolHive prints in workload URLs, as seen from ToolHive
        itself. Defaults to ``127.0.0.1``.
    ``runtime_host``
        The host this deployment must dial to reach the same workload.
        Defaults to ``host.docker.internal``.

Both hosts are bare hostnames: no scheme, port, or path.

The two-host split exists because ToolHive advertises loopback URLs that are
meaningful only inside its own container. Endpoint rewriting is therefore
deliberately narrow: a workload URL is accepted only if its host equals
``reported_host``, and only that host is swapped for ``runtime_host``; the port
and path are preserved and the scheme becomes ``mcp+http(s)``. A workload
pointing anywhere else is refused rather than rewritten, so a compromised
registry cannot redirect this deployment at an unrelated address. For a source
registered as public, ``runtime_host`` must equal the registry's own host,
which removes the rewrite as a pivot entirely.

Onboarding delegates: the rewritten endpoint is handed to the WoT runtime,
which speaks MCP and returns the Thing Description. This provider never
authors a document itself, and supports neither acquisition nor refresh.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any
from urllib.parse import urlparse, urlunparse

from wotbot.discovery.detection import DetectionContext
from wotbot.discovery.errors import ProviderError, SourceProtocolError
from wotbot.discovery.http import BoundedHttpClient
from wotbot.discovery.models import (
    CandidateDraft,
    OnboardingResult,
    ProviderConfigSpec,
    SearchIntent,
    SourceDefinition,
)
from wotbot.discovery.providers.base import (
    DiscoveryProvider,
    OnboardingRuntime,
    items,
    source_json,
    text,
)
from wotbot.discovery.search import prepare_search_intent, rank_candidates


class ToolHiveProvider(DiscoveryProvider):
    name = "toolhive"
    capabilities = ("detect", "search", "onboard")
    detect_priority = 20
    config = ProviderConfigSpec(
        fields=frozenset({"url", "reported_host", "runtime_host"}),
        url_fields=("url",),
        text_defaults=(
            ("reported_host", "127.0.0.1"),
            ("runtime_host", "host.docker.internal"),
        ),
        title="ToolHive registry",
    )

    def normalize_config(self, config: dict[str, Any]) -> dict[str, Any]:
        normalized = super().normalize_config(config)
        for field in ("reported_host", "runtime_host"):
            value = str(normalized[field])
            if not value or "://" in value or "/" in value or ":" in value:
                raise ValueError(f"Provider requires '{field}' to be a hostname without a port")
        return normalized

    async def inspect_public(self, context: DetectionContext) -> SourceDefinition | None:
        return await detect_toolhive(context.root, public_http=context.http, notes=context.note)

    async def search(
        self,
        source: SourceDefinition,
        intent: SearchIntent,
        limit: int,
        *,
        public_http: BoundedHttpClient | None = None,
    ) -> list[CandidateDraft]:
        payload = await source_json(
            "GET",
            f"{source.get('url')}/api/v1beta/workloads",
            source=source,
            public_http=public_http,
        )
        candidates: list[tuple[CandidateDraft, str]] = []
        for workload in items(payload):
            if str(workload.get("status") or "").casefold() != "running":
                continue
            name = str(workload.get("name") or workload.get("id") or "").strip()
            endpoint = str(workload.get("url") or workload.get("endpoint") or "").strip()
            if not name or not endpoint:
                continue
            package = text(workload.get("package") or workload.get("image"))
            candidate = CandidateDraft(
                provider=self.name,
                source_id=source.id,
                external_id=name,
                kind="mcp-server",
                title=name,
                summary=package or "Running MCP server",
                payload={"endpoint": self.runtime_endpoint(source, endpoint)},
            )
            candidates.append((candidate, f"{name} {package} {endpoint}"))
        return rank_candidates(intent, candidates, limit=limit, require_match=True)

    @staticmethod
    def runtime_endpoint(source: SourceDefinition, endpoint: str) -> str:
        parsed = urlparse(endpoint)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
        ):
            raise SourceProtocolError("ToolHive returned an invalid MCP endpoint URL")
        reported_host = _hostname(str(source.get("reported_host")))
        if _hostname(parsed.hostname) != reported_host:
            raise SourceProtocolError(
                "ToolHive endpoint host does not match its configured reported host"
            )
        runtime_host = _hostname(str(source.get("runtime_host")))
        source_host = _hostname(str(urlparse(str(source.get("url"))).hostname or ""))
        if source.network_access == "public" and runtime_host != source_host:
            raise SourceProtocolError("Public ToolHive runtime host must match its registry host")
        port = f":{parsed.port}" if parsed.port else ""
        return urlunparse(
            (
                f"mcp+{parsed.scheme}",
                f"{runtime_host}{port}",
                parsed.path,
                "",
                parsed.query,
                "",
            )
        )

    async def onboarding_document(
        self,
        source: SourceDefinition,
        candidate: CandidateDraft,
        *,
        runtime: OnboardingRuntime,
    ) -> OnboardingResult:
        del source
        endpoint = str(candidate.payload.get("endpoint") or "")
        if not endpoint:
            raise SourceProtocolError("Candidate has no self-describing endpoint")
        response = await runtime.describe_endpoint(url=endpoint)
        document = response.get("document") if isinstance(response, dict) else None
        if not isinstance(document, dict):
            raise SourceProtocolError("Endpoint did not return a Thing Description")
        return OnboardingResult(document=document)


def _hostname(value: str) -> str:
    return value.strip().casefold().rstrip(".")


async def detect_toolhive(
    root: str,
    *,
    public_http: BoundedHttpClient | None,
    notes: Any = None,
) -> SourceDefinition | None:
    """Probe one origin for a ToolHive workloads API.

    Shared by public detection and the private registration path, which reaches
    a host the public address policy would refuse.
    """

    def note(message: str) -> None:
        if notes is not None:
            notes(message)

    parsed = urlparse(root)
    runtime_host = (
        "host.docker.internal"
        if parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        else str(parsed.hostname or "host.docker.internal")
    )
    provisional = SourceDefinition(
        id=root,
        external_id=root,
        provider="toolhive",
        title=f"ToolHive at {parsed.netloc}",
        description="MCP servers managed by ToolHive.",
        tags=("ToolHive", "MCP", "external source"),
        config={"url": root, "reported_host": "127.0.0.1", "runtime_host": runtime_host},
        network_access="public" if public_http is not None else "private",
    )
    try:
        payload = await source_json(
            "GET",
            f"{root}/api/v1beta/workloads",
            source=provisional,
            public_http=public_http,
        )
        if not isinstance(payload, list) and not (
            isinstance(payload, dict)
            and any(isinstance(payload.get(key), list) for key in ("data", "items", "workloads"))
        ):
            raise SourceProtocolError("ToolHive workload response has an unexpected shape")
        workloads = items(payload)
        reported_host = next(
            (
                str(urlparse(str(workload.get("url") or workload.get("endpoint") or "")).hostname)
                for workload in workloads
                if urlparse(str(workload.get("url") or workload.get("endpoint") or "")).hostname
            ),
            "127.0.0.1",
        )
        source = replace(
            provisional,
            config={**provisional.config, "reported_host": reported_host},
        )
        # Validate the response shape and endpoint conversion with the provider itself.
        await ToolHiveProvider().search(
            source,
            prepare_search_intent("", source),
            1,
            public_http=public_http,
        )
    except (ProviderError, json.JSONDecodeError) as exc:
        note(f"ToolHive probe failed: {exc}")
        return None
    note("Detected ToolHive at /api/v1beta/workloads")
    return source
