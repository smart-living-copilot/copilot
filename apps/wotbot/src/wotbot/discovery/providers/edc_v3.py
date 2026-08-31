"""EDC v3: assets offered through an Eclipse Dataspace Connector.

Expects an EDC Management API v3 and speaks four of its endpoints:
``POST /v3/catalog/request``, ``POST /v3/contractnegotiations``,
``POST /v3/transferprocesses``, and ``GET /v3/edrs/{id}/dataaddress``.

Configuration
    ``management_url``
        This deployment's own EDC management API. Required.
    ``counter_party_address``
        The partner connector's protocol endpoint. Required, and it is this
        source's canonical identity rather than ``management_url``.
    ``counter_party_id``
        The partner's DID or BPN. Optional for a plain EDC, which ignores it,
        but **required by Tractus-X connectors**, which reject a request that
        does not name the provider. Sent only when set.
    ``protocol``
        Dataspace protocol name. Defaults to ``dataspace-protocol-http``.
    ``api_key_header``
        Header carrying the management API key. Defaults to ``X-Api-Key``.
    ``poll_interval_seconds`` / ``poll_timeout_seconds``
        Negotiation and transfer polling. Default to 2 and 120.

A credential is mandatory: the management API is privileged, so this provider
declares ``requires_secret`` and defaults to the ``apikey`` scheme. It also
does not detect. A dataspace membership is arranged out of band, so a source is
registered explicitly and never inferred from a pasted URL.

Response parsing is deliberately tolerant, because the same connector family
answers in several shapes: a catalog may arrive as one object or a list of
them, a single dataset may be inlined rather than wrapped, and fields may be
compacted (``state``) or expanded (``edc:state``) depending on the
distribution. ``authKey`` is ambiguous in particular -- a header name in a
plain EDC, the token itself in Tractus-X -- so it is read as a token only when
no separate value field is present and it is not a bare header name.

Only datasets carrying an ``odrl:hasPolicy`` offer are shown, because a dataset
without one cannot be negotiated for. Onboarding produces a Thing with a single
download action; the contract is negotiated at invocation, not at onboarding,
so nothing is agreed to merely by browsing.

Acquisition is the sequence negotiate, poll to FINALIZED or VERIFIED, request
transfer, poll to STARTED or COMPLETED, then read the endpoint data reference.
Two consequences matter. It is slow and bounded by ``poll_timeout_seconds``,
which is why the request budget is raised to 128 and why it should eventually
run as a job rather than inside a request. And the reference carries a
short-lived bearer secret, so its header name is validated against a denylist
and a token grammar before use, and its expiry becomes the download's TTL.
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlparse

from wotbot.discovery.errors import SourceProtocolError, SourceUnavailableError
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
    TD_CONTEXT,
    WOTBOT_CONTEXT,
    DiscoveryProvider,
    OnboardingRuntime,
    provider_download_action,
    provider_thing_id,
    source_json,
    text,
)
from wotbot.discovery.search import rank_candidates

JSONLD_CONTEXT = {"@vocab": "https://w3id.org/edc/v0.0.1/ns/"}
EDC_PREFIX = "edc:"
FORBIDDEN_SECRET_HEADERS = {"host", "content-length", "connection", "transfer-encoding"}
# Names a connector would use for the header itself. An ``authKey`` holding one
# of these and nothing else is a classic EDR missing its token, not a token.
AUTH_HEADER_NAMES = {"authorization", "x-api-key", "x-auth-token", "apikey"}


class EdcV3Provider(DiscoveryProvider):
    name = "edc-v3"
    # Acquisition polls negotiation and transfer state, so EDC needs a larger
    # bounded request budget than ordinary catalog providers.
    public_max_requests = 128
    config = ProviderConfigSpec(
        fields=frozenset(
            {
                "management_url",
                "counter_party_address",
                "counter_party_id",
                "protocol",
                "api_key_header",
                "poll_interval_seconds",
                "poll_timeout_seconds",
            }
        ),
        url_fields=("management_url", "counter_party_address"),
        text_defaults=(
            ("protocol", "dataspace-protocol-http"),
            ("api_key_header", "X-Api-Key"),
            ("counter_party_id", ""),
        ),
        float_defaults=(("poll_interval_seconds", 2), ("poll_timeout_seconds", 120)),
        requires_secret=True,
        title="EDC v3 catalog",
    )

    def external_identity(self, config: dict[str, Any]) -> str:
        return str(config.get("counter_party_address") or "")

    def _party(self, source: SourceDefinition) -> dict[str, str]:
        """The counterparty fields every request to a connector carries.

        Tractus-X connectors reject a request that does not name the provider's
        DID or BPN, while a plain EDC ignores the field, so it is sent whenever
        the source has one and omitted otherwise.
        """

        party = {
            "counterPartyAddress": str(source.get("counter_party_address")),
            "protocol": str(source.get("protocol", "dataspace-protocol-http")),
        }
        identity = str(source.get("counter_party_id") or "").strip()
        if identity:
            party["counterPartyId"] = identity
        return party

    def _catalog_request(
        self,
        source: SourceDefinition,
        *,
        limit: int,
        external_id: str | None = None,
    ) -> dict[str, Any]:
        filters: list[dict[str, str]] = []
        if external_id:
            filters.append({"operandLeft": "@id", "operator": "=", "operandRight": external_id})
        return {
            "@context": JSONLD_CONTEXT,
            "@type": "CatalogRequest",
            **self._party(source),
            "querySpec": {"offset": 0, "limit": limit, "filterExpression": filters},
        }

    async def _catalog(
        self,
        source: SourceDefinition,
        *,
        limit: int,
        external_id: str | None = None,
        public_http: BoundedHttpClient | None = None,
    ) -> list[dict[str, Any]]:
        catalog = await source_json(
            "POST",
            f"{source.get('management_url')}/v3/catalog/request",
            source=source,
            public_http=public_http,
            body=self._catalog_request(source, limit=limit, external_id=external_id),
        )
        # A connector may answer with a single catalog or a list of them, and
        # a catalog with one dataset may inline it rather than wrap it.
        catalogs = catalog if isinstance(catalog, list) else [catalog]
        datasets: list[Any] = []
        for entry in catalogs:
            if not isinstance(entry, dict):
                continue
            found = field(entry, "dcat:dataset", "dataset") or []
            datasets.extend(found if isinstance(found, list) else [found])
        return [item for item in datasets if isinstance(item, dict)]

    async def search(
        self,
        source: SourceDefinition,
        intent: SearchIntent,
        limit: int,
        *,
        public_http: BoundedHttpClient | None = None,
    ) -> list[CandidateDraft]:
        candidates: list[tuple[CandidateDraft, str]] = []
        for dataset in await self._catalog(
            source,
            limit=max(50, limit),
            public_http=public_http,
        ):
            external_id = str(dataset.get("@id") or dataset.get("id") or "").strip()
            title = text(field(dataset, "dct:title", "title")) or external_id
            summary = text(field(dataset, "dct:description", "description"))
            if not external_id:
                continue
            if not self._policy(dataset):
                continue
            candidate = CandidateDraft(
                provider=self.name,
                source_id=source.id,
                external_id=external_id,
                kind="dataspace-asset",
                title=title,
                summary=summary,
            )
            candidates.append((candidate, f"{external_id} {title} {summary}"))
        return rank_candidates(intent, candidates, limit=limit, require_match=True)

    async def onboarding_document(
        self,
        source: SourceDefinition,
        candidate: CandidateDraft,
        *,
        runtime: OnboardingRuntime,
    ) -> OnboardingResult:
        del source, runtime
        thing_id = provider_thing_id(self.name, candidate.source_id, candidate.external_id)
        action_name = "download_asset"
        return OnboardingResult(
            document={
                "@context": [TD_CONTEXT, WOTBOT_CONTEXT],
                "id": thing_id,
                "title": candidate.title,
                "description": candidate.summary,
                "security": ["nosec_sc"],
                "securityDefinitions": {"nosec_sc": {"scheme": "nosec"}},
                "actions": {
                    action_name: provider_download_action(
                        thing_id,
                        action_name=action_name,
                        title="Download asset",
                        description=(
                            "Negotiate access through the dataspace and return the asset content."
                        ),
                    )
                },
            }
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
        del resource_id
        datasets = await self._catalog(
            source,
            limit=1,
            external_id=external_id,
            public_http=public_http,
        )
        dataset = next(
            (
                item
                for item in datasets
                if str(item.get("@id") or item.get("id") or "").strip() == external_id
            ),
            None,
        )
        if dataset is None:
            raise SourceProtocolError("The selected EDC asset is no longer offered")
        policy = self._policy(dataset)
        if not policy:
            raise SourceProtocolError("The selected EDC asset has no current contract offer")
        negotiation = await source_json(
            "POST",
            f"{source.get('management_url')}/v3/contractnegotiations",
            source=source,
            public_http=public_http,
            body={
                "@context": JSONLD_CONTEXT,
                "@type": "ContractRequest",
                **self._party(source),
                "policy": policy,
            },
        )
        negotiation_id = response_id(negotiation, "id")
        negotiated = await self._poll(
            source,
            f"{source.get('management_url')}/v3/contractnegotiations/{quote(negotiation_id, safe='')}",
            success={"FINALIZED", "VERIFIED"},
            failure={"TERMINATED", "ERROR"},
            public_http=public_http,
        )
        agreement_id = text(
            field(negotiated, "contractAgreementId", "agreementId")
            or (field(negotiated, "contractAgreement") or {}).get("@id")
        )
        if not agreement_id:
            raise SourceProtocolError("EDC negotiation finalized without a contract agreement id")
        transfer = await source_json(
            "POST",
            f"{source.get('management_url')}/v3/transferprocesses",
            source=source,
            public_http=public_http,
            body={
                "@context": JSONLD_CONTEXT,
                "@type": "TransferRequest",
                **self._party(source),
                "contractId": agreement_id,
                "transferType": "HttpData-PULL",
            },
        )
        transfer_id = response_id(transfer, "id")
        await self._poll(
            source,
            f"{source.get('management_url')}/v3/transferprocesses/{quote(transfer_id, safe='')}",
            success={"STARTED", "COMPLETED"},
            failure={"TERMINATED", "DEPROVISIONED", "ERROR"},
            public_http=public_http,
        )
        address = await source_json(
            "GET",
            f"{source.get('management_url')}/v3/edrs/{quote(transfer_id, safe='')}/dataaddress",
            source=source,
            public_http=public_http,
        )
        endpoint = text(field(address, "endpoint", "baseUrl"))
        headers = secret_headers(address)
        parsed_endpoint = urlparse(endpoint)
        if (
            parsed_endpoint.scheme not in {"http", "https"}
            or not parsed_endpoint.hostname
            or parsed_endpoint.username
            or parsed_endpoint.password
        ):
            raise SourceProtocolError("EDC returned an invalid endpoint data reference URL")
        ttl = edr_ttl(address)
        filename = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-") or "download"
        return (
            DownloadRecord(
                endpoint=endpoint,
                headers=headers,
                public=public_http is not None,
                filename=filename,
            ),
            ttl,
        )

    @staticmethod
    def _policy(dataset: dict[str, Any]) -> dict[str, Any] | None:
        policies = field(dataset, "odrl:hasPolicy", "hasPolicy") or []
        if isinstance(policies, dict):
            policies = [policies]
        return next(
            (
                item
                for item in policies
                if isinstance(item, dict)
                and isinstance(item.get("@id") or item.get("id"), str)
                and str(item.get("@id") or item.get("id")).strip()
            ),
            None,
        )

    async def _poll(
        self,
        source: SourceDefinition,
        url: str,
        *,
        success: set[str],
        failure: set[str],
        public_http: BoundedHttpClient | None = None,
    ) -> dict[str, Any]:
        deadline = asyncio.get_running_loop().time() + float(
            source.get("poll_timeout_seconds", 120)
        )
        while asyncio.get_running_loop().time() < deadline:
            payload = await source_json(
                "GET",
                url,
                source=source,
                public_http=public_http,
            )
            if not isinstance(payload, dict):
                raise SourceProtocolError("EDC returned an invalid process state")
            state = text(field(payload, "state", "stateName")).upper()
            if state in success:
                return payload
            if state in failure:
                raise SourceProtocolError(f"EDC process failed in state '{state}'")
            await asyncio.sleep(float(source.get("poll_interval_seconds", 2)))
        raise SourceUnavailableError("EDC process timed out")


def field(payload: Any, *names: str) -> Any:
    """Read the first present field, accepting the ``edc:`` JSON-LD prefix.

    Whether a management API expands or compacts its response depends on the
    distribution and its version, so the same value arrives as ``state`` or
    ``edc:state`` from connectors that are otherwise identical.
    """

    if not isinstance(payload, dict):
        return None
    for name in names:
        for key in (name, f"{EDC_PREFIX}{name}"):
            if payload.get(key) is not None:
                return payload[key]
    return None


def response_id(payload: Any, fallback: str) -> str:
    if not isinstance(payload, dict):
        raise SourceProtocolError("EDC returned an invalid process response")
    value = text(payload.get("@id") or payload.get("id"))
    if not value:
        raise SourceProtocolError(f"EDC response is missing {fallback}")
    return value


def secret_headers(address: Any) -> dict[str, str]:
    """Build the single header that authorizes the acquired endpoint.

    ``authKey`` is ambiguous across distributions: a plain EDC uses it for the
    header *name* alongside ``authCode``, while Tractus-X uses it as a fallback
    for the token itself. The presence of a separate value field decides which,
    so a token is never mistaken for a header name.
    """

    if not isinstance(address, dict):
        raise SourceProtocolError("EDC returned an incomplete endpoint data reference")
    separate_value = text(field(address, "authCode", "authorization"))
    if separate_value:
        header_name = text(field(address, "authKey")) or "Authorization"
        header_value = separate_value
    else:
        # No separate value: Tractus-X puts the token in authKey. A bare header
        # name there means the reference simply arrived without its secret.
        header_name = "Authorization"
        candidate = text(field(address, "authKey"))
        header_value = "" if candidate.casefold() in AUTH_HEADER_NAMES else candidate
    if not header_value:
        raise SourceProtocolError("EDC returned an incomplete endpoint data reference")
    if (
        not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", header_name)
        or header_name.casefold() in FORBIDDEN_SECRET_HEADERS
    ):
        raise SourceProtocolError("EDC returned an unsafe authorization header name")
    return {header_name: header_value}


def edr_ttl(address: dict[str, Any], *, now: float | None = None) -> int | None:
    if "expiresIn" in address:
        try:
            ttl = int(float(address["expiresIn"]))
        except (TypeError, ValueError) as exc:
            raise SourceProtocolError(
                "EDC returned an invalid endpoint data reference expiration"
            ) from exc
        if ttl <= 0:
            raise SourceProtocolError("EDC endpoint data reference has expired")
        return ttl
    raw_expiry = next(
        (
            address[key]
            for key in ("expiresAt", "expiration", "expirationDate")
            if address.get(key) is not None
        ),
        None,
    )
    if raw_expiry is None:
        return None
    try:
        text_expiry = str(raw_expiry).strip()
        if isinstance(raw_expiry, str) and not text_expiry.replace(".", "", 1).isdigit():
            expires_at = datetime.fromisoformat(text_expiry).timestamp()
        else:
            expires_at = float(raw_expiry)
            if expires_at > 10_000_000_000:
                expires_at /= 1000
    except (TypeError, ValueError, OverflowError) as exc:
        raise SourceProtocolError(
            "EDC returned an invalid endpoint data reference expiration"
        ) from exc
    ttl = int(expires_at - (time.time() if now is None else now))
    if ttl <= 0:
        raise SourceProtocolError("EDC endpoint data reference has expired")
    return ttl
