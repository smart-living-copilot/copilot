from __future__ import annotations

from typing import Any

import aiohttp

from copilot.core.config import Settings


def _setting_value(settings: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if hasattr(settings, name):
            return getattr(settings, name)
    return default


class RdfServiceClient:
    def __init__(self, settings: Settings | Any) -> None:
        self._base_url = str(
            _setting_value(
                settings,
                "RDF_SERVICE_URL",
                "rdf_service_url",
                default="http://localhost:8124",
            )
        ).rstrip("/")
        token = _setting_value(settings, "internal_api_key", "INTERNAL_API_KEY", default="")
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._timeout = aiohttp.ClientTimeout(
            total=_setting_value(
                settings,
                "RDF_QUERY_TIMEOUT_SECONDS",
                "rdf_query_timeout_seconds",
                default=20,
            )
        )

    async def health(self) -> dict[str, Any]:
        return await self._request("GET", "/health")

    async def query(
        self,
        *,
        query: str,
        limit: int,
        use_default_graph_as_union: bool = True,
        endpoints: list[str] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/rdf/query",
            {
                "query": query,
                "limit": limit,
                "use_default_graph_as_union": use_default_graph_as_union,
                "endpoints": endpoints or [],
            },
        )

    async def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            async with session.request(
                method,
                url,
                json=payload,
                headers=self._headers,
            ) as response:
                data = await response.json(content_type=None)
                if response.status >= 400:
                    detail = data.get("detail") if isinstance(data, dict) else None
                    raise ValueError(
                        detail or f"rdf_service request failed with status {response.status}"
                    )
                if not isinstance(data, dict):
                    raise ValueError("rdf_service returned a non-object response")
                return data
