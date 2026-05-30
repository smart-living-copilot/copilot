from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from copilot.core.config import Settings
from copilot.search.embeddings import create_openai_embeddings
from copilot.search.vector_store import SearchVectorStore
from copilot.things.store import get_thing


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    items: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            items.append(item)
    return items


class ThingSearchService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._embeddings = (
            create_openai_embeddings(
                base_url=self._settings.OPENAI_EMBEDDING_API_BASE_URL,
                api_key=self._settings.OPENAI_EMBEDDING_API_KEY,
                model=self._settings.OPENAI_EMBEDDING_MODEL,
            )
            if self._settings.OPENAI_EMBEDDING_API_KEY
            else None
        )
        self._vector_store = SearchVectorStore(
            embeddings=self._embeddings,
            embedding_dimensions=self._settings.SEARCH_VECTOR_DIMENSIONS,
        )

    async def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        results = await self._vector_store.query_similar(query, limit=k)
        return [
            {
                "id": result.metadata.get("id", ""),
                "title": result.metadata.get("title", ""),
                "description": result.metadata.get("description", ""),
                "tags": result.metadata.get("tags", []),
                "score": round(result.score, 4),
                "summary": result.document,
            }
            for result in results
        ]

    async def get_index_status(
        self,
        thing_id: str,
        document_hash: str,
    ) -> dict[str, Any]:
        entry = await self._vector_store.get_device_chunk(thing_id)
        if entry is None:
            return {"thing_id": thing_id, "indexed": False}

        summary = entry.page_content if entry.page_content.strip() else None
        metadata = entry.metadata
        td_hash = metadata.get("tdHash", "")
        td_hash_match = bool(td_hash) and td_hash == document_hash
        return {
            "thing_id": thing_id,
            "indexed": True,
            "stale": not td_hash_match,
            "indexed_at": metadata.get("indexedAt"),
            "summary_source": metadata.get("summarySource"),
            "summary_model": metadata.get("summaryModel"),
            "prompt_version": metadata.get("promptVersion"),
            "td_hash_match": td_hash_match,
            "summary": summary,
            "location_candidates": _coerce_string_list(
                metadata.get("locationCandidates")
            ),
            "property_names": _coerce_string_list(metadata.get("propertyNames")),
            "action_names": _coerce_string_list(metadata.get("actionNames")),
            "event_names": _coerce_string_list(metadata.get("eventNames")),
        }

    @property
    def vector_store(self) -> SearchVectorStore:
        return self._vector_store

    async def close(self) -> None:
        if self._embeddings is not None:
            await self._embeddings.close()


class SearchQueryService:
    def __init__(
        self,
        session: Session,
        search_service: ThingSearchService,
    ) -> None:
        self._session = session
        self._search_service = search_service

    async def search(self, *, query: str, k: int) -> dict[str, Any]:
        items = await self._search_service.search(query=query, k=k)
        return {"items": items, "query": query}

    async def get_index_status(self, thing_id: str) -> dict[str, Any]:
        thing = get_thing(self._session, thing_id)
        if thing is None:
            raise HTTPException(status_code=404, detail="Thing not found")

        return await self._search_service.get_index_status(
            thing_id,
            thing.document_hash,
        )
