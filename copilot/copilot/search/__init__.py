from __future__ import annotations

from copilot.search.service import SearchQueryService, ThingSearchService

_active_search_service: ThingSearchService | None = None


def set_active_search_service(service: ThingSearchService | None) -> None:
    global _active_search_service
    _active_search_service = service


def get_active_search_service() -> ThingSearchService | None:
    return _active_search_service


__all__ = [
    "SearchQueryService",
    "ThingSearchService",
    "get_active_search_service",
    "set_active_search_service",
]
