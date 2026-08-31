"""DCAT: datasets described by one RDF catalog document.

Expects a single RDF document at the configured URL, parsed as Turtle when the
response is ``text/turtle`` or the URL ends in ``.ttl``, and as RDF/XML
otherwise. Datasets are the subjects typed ``dcat:Dataset``; distributions come
from ``dcat:distribution``, taking ``dcat:downloadURL`` and falling back to
``dcat:accessURL``.

Configuration
    ``url``
        The catalog document itself, not the portal. Required.
    ``portal_url``
        The human-facing page to link back to. Optional.

Unlike uData there is no server-side query: DCAT is a static file, so the whole
graph is fetched, bounded at 1 MiB, and ranked in this process. That bound is
the real constraint on which catalogs this provider suits — a large national
catalog will be refused rather than truncated, and belongs behind an API that
can be queried.

Distributions whose URL is not plain HTTP(S), or which carry embedded
credentials, are dropped. Resource ids are derived from the distribution URL,
so acquisition re-fetches the graph and re-resolves the dataset URI and
resource id; a dataset that left the catalog fails rather than resolving to a
stale distribution.

Detection is the last probe tried: it guesses catalog URLs from homepage links
and then ``/catalog.rdf``, and accepts any document rdflib can parse, so it is
deliberately ordered behind every more specific provider. There is no refresh.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from rdflib import Graph, URIRef
from rdflib.namespace import DCAT, DCTERMS, RDF

from wotbot.discovery.detection import DetectionContext, origin
from wotbot.discovery.errors import (
    ProviderError,
    SourceAuthenticationError,
    SourceProtocolError,
    SourceUnavailableError,
)
from wotbot.discovery.http import BoundedHttpClient
from wotbot.discovery.models import (
    CandidateDraft,
    DownloadRecord,
    OnboardingResult,
    ProviderConfigSpec,
    SearchIntent,
    SourceDefinition,
)
from wotbot.discovery.providers.base import (
    DiscoveryProvider,
    OnboardingRuntime,
    credential_headers,
    dataset_document,
    source_client,
    stable_resource_id,
    text,
)
from wotbot.discovery.search import prepare_search_intent, rank_candidates

# The whole catalog is parsed in memory, so this bound decides which catalogs
# this provider can serve at all. It was 1 MiB, which measurement showed
# rejects real national catalogs -- opendata.swiss alone is ~1.6 MiB -- leaving
# the provider with effectively no real-world coverage. 8 MiB is still well
# inside what rdflib parses comfortably; a catalog past it belongs behind a
# queryable API rather than a static document.
_MAX_CATALOG_BYTES = 8 * 1024 * 1024


def graph_resources(graph: Graph, dataset: Any, *, limit: int = 20) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for distribution in graph.objects(dataset, DCAT.distribution):
        href = next(iter(graph.objects(distribution, DCAT.downloadURL)), None)
        href = href or next(iter(graph.objects(distribution, DCAT.accessURL)), None)
        if not isinstance(href, URIRef):
            continue
        url = str(href)
        parsed = urlparse(url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            continue
        media_type = text(next(iter(graph.objects(distribution, DCAT.mediaType)), ""))
        format_name = text(next(iter(graph.objects(distribution, DCTERMS.format)), ""))
        title = text(next(iter(graph.objects(distribution, DCTERMS.title)), "")) or "Distribution"
        description = text(next(iter(graph.objects(distribution, DCTERMS.description)), ""))
        modified = text(next(iter(graph.objects(distribution, DCTERMS.modified)), ""))
        descriptor: dict[str, Any] = {
            "id": stable_resource_id(url),
            "title": title[:200],
            "description": description[:1000],
            "url": url,
            "media_type": media_type[:200],
            "format": format_name[:100],
            "filename": PurePosixPath(parsed.path).name[:200] or "download",
            "modified": modified[:100],
        }
        raw_size = next(iter(graph.objects(distribution, DCAT.byteSize)), None)
        try:
            if raw_size is not None and int(str(raw_size)) >= 0:
                descriptor["size_bytes"] = int(str(raw_size))
        except ValueError:
            pass
        results.append(descriptor)
        if len(results) >= limit:
            break
    return results


class DcatProvider(DiscoveryProvider):
    name = "dcat"
    capabilities = ("detect", "search", "onboard")
    detect_priority = 60
    public_max_bytes = _MAX_CATALOG_BYTES
    config = ProviderConfigSpec(
        fields=frozenset({"url", "portal_url"}),
        url_fields=("url",),
        optional_url_fields=("portal_url",),
        title="DCAT catalog",
    )

    async def inspect_public(self, context: DetectionContext) -> SourceDefinition | None:
        homepage = await context.homepage()
        if not homepage.ok:
            return None
        guesses = [
            link
            for link in homepage.links
            if re.search(r"(catalog|dcat).*(rdf|xml|ttl)|\.(rdf|ttl)$", link, re.IGNORECASE)
        ]
        guesses.append(f"{homepage.root}/catalog.rdf")
        for catalog_url in list(dict.fromkeys(guesses))[:3]:
            if origin(catalog_url) != homepage.root:
                continue
            source = SourceDefinition(
                id=catalog_url,
                external_id=catalog_url,
                provider=self.name,
                config={"url": catalog_url, "portal_url": homepage.payload.url},
                **homepage.metadata(),  # type: ignore[arg-type]
            )
            try:
                await self.search(
                    source, prepare_search_intent("", source), 1, public_http=context.http
                )
            except (ProviderError, SyntaxError) as exc:
                context.note(f"DCAT probe failed at {catalog_url}: {exc}")
                continue
            context.note(f"Detected a DCAT catalog at {catalog_url}")
            return source
        return None

    async def _graph(
        self,
        source: SourceDefinition,
        *,
        public_http: BoundedHttpClient | None,
    ) -> Graph:
        client = public_http or source_client(source, max_bytes=_MAX_CATALOG_BYTES)
        secrets = credential_headers(source)
        response = await client.get(
            str(source.get("url")),
            headers={"Accept": "application/rdf+xml,text/turtle", **secrets},
            max_bytes=_MAX_CATALOG_BYTES,
            credentialed=bool(secrets),
        )
        if response.status in {401, 403}:
            raise SourceAuthenticationError(f"DCAT source '{source.id}' rejected its credential")
        if response.status < 200 or response.status >= 300:
            raise SourceUnavailableError(f"DCAT catalog returned HTTP {response.status}")
        body, content_type = response.body, response.content_type
        graph = Graph()
        source_url = str(source.get("url"))
        rdf_format = "turtle" if "turtle" in content_type or source_url.endswith(".ttl") else "xml"
        graph.parse(data=body, format=rdf_format, publicID=source_url)
        return graph

    async def search(
        self,
        source: SourceDefinition,
        intent: SearchIntent,
        limit: int,
        *,
        public_http: BoundedHttpClient | None = None,
    ) -> list[CandidateDraft]:
        graph = await self._graph(source, public_http=public_http)
        candidates: list[tuple[CandidateDraft, str]] = []
        for dataset in graph.subjects(RDF.type, DCAT.Dataset):
            title = text(next(iter(graph.objects(dataset, DCTERMS.title)), ""))
            summary = text(next(iter(graph.objects(dataset, DCTERMS.description)), ""))
            descriptors = graph_resources(graph, dataset)
            candidate = CandidateDraft(
                provider=self.name,
                source_id=source.id,
                external_id=str(dataset),
                kind="dataset",
                title=title or str(dataset),
                summary=summary,
                links=tuple(
                    {
                        "title": item["title"],
                        "url": item["url"],
                        "media_type": item["media_type"],
                    }
                    for item in descriptors[:6]
                ),
                payload={"resources": descriptors},
            )
            keywords = " ".join(text(value) for value in graph.objects(dataset, DCAT.keyword))
            publisher = " ".join(text(value) for value in graph.objects(dataset, DCTERMS.publisher))
            distributions = " ".join(
                f"{item['title']} {item['description']} {item['format']}" for item in descriptors
            )
            candidates.append(
                (candidate, f"{dataset} {title} {summary} {keywords} {publisher} {distributions}")
            )
        return rank_candidates(intent, candidates, limit=limit, require_match=True)

    async def onboarding_document(
        self,
        source: SourceDefinition,
        candidate: CandidateDraft,
        *,
        runtime: OnboardingRuntime,
    ) -> OnboardingResult:
        del source, runtime
        descriptors = candidate.payload.get("resources")
        return OnboardingResult(
            document=dataset_document(
                candidate,
                [dict(item) for item in descriptors if isinstance(item, dict)]
                if isinstance(descriptors, list)
                else [],
            )
        )

    async def acquire(
        self,
        source: SourceDefinition,
        *,
        external_id: str,
        title: str,
        resource_id: str | None,
        public_http: BoundedHttpClient | None = None,
    ) -> tuple[DownloadRecord, int | None]:
        if not resource_id:
            raise ValueError("resource_id is required")
        graph = await self._graph(source, public_http=public_http)
        dataset = URIRef(external_id)
        if (dataset, RDF.type, DCAT.Dataset) not in graph:
            raise SourceProtocolError("The selected DCAT dataset is no longer available")
        descriptor = next(
            (item for item in graph_resources(graph, dataset) if item["id"] == resource_id),
            None,
        )
        if descriptor is None:
            raise SourceProtocolError("The selected dataset resource is no longer available")
        path_name = PurePosixPath(urlparse(descriptor["url"]).path).name
        fallback = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-") or "download"
        return (
            DownloadRecord(
                endpoint=descriptor["url"],
                public=public_http is not None,
                content_type=descriptor["media_type"] or "application/octet-stream",
                filename=path_name or fallback,
                size_bytes=descriptor.get("size_bytes"),
            ),
            None,
        )
