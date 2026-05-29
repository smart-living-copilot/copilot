from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings


MetadataScalar = str | int | float | bool


@dataclass(frozen=True)
class SearchIndexDocument:
    page_content: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class SearchIndexMatch:
    chunk_id: str
    document: str
    metadata: dict[str, Any]
    score: float


def _coerce_metadata(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _distance_to_score(value: Any) -> float:
    try:
        distance = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 1.0 / (1.0 + max(distance, 0.0))


def _is_metadata_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool))


def _sanitize_metadata_for_chroma(metadata: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, MetadataScalar | list[MetadataScalar]] = {}
    for key, value in metadata.items():
        if value is None:
            continue

        if _is_metadata_scalar(value):
            sanitized[key] = value
            continue

        if isinstance(value, list):
            items = [item for item in value if _is_metadata_scalar(item)]
            if items:
                sanitized[key] = items

    return sanitized


def _document_to_langchain_document(
    chunk_id: str,
    document: SearchIndexDocument,
) -> Document:
    return Document(
        id=chunk_id,
        page_content=document.page_content,
        metadata=_sanitize_metadata_for_chroma(document.metadata),
    )


class SearchVectorStore:
    def __init__(
        self,
        *,
        embeddings: Embeddings | None,
        collection_name: str,
        persist_directory: str,
    ) -> None:
        self._embeddings = embeddings
        self._persist_directory = Path(persist_directory)
        self._vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=str(self._persist_directory),
        )

    async def ensure_schema(self) -> None:
        self._persist_directory.mkdir(parents=True, exist_ok=True)

    async def query_similar(
        self,
        query: str,
        *,
        limit: int,
    ) -> list[SearchIndexMatch]:
        await self.ensure_schema()
        self._require_embeddings()
        matches = await self._vector_store.asimilarity_search_with_score(
            query,
            k=limit,
        )
        return [
            SearchIndexMatch(
                chunk_id=document.id or "",
                document=document.page_content,
                metadata=_coerce_metadata(document.metadata),
                score=_distance_to_score(score),
            )
            for document, score in matches
        ]

    async def get_device_chunk(self, thing_id: str) -> SearchIndexDocument | None:
        await self.ensure_schema()
        documents = await self._vector_store.aget_by_ids([thing_id])
        if not documents:
            return None
        document = documents[0]
        return SearchIndexDocument(
            page_content=document.page_content,
            metadata=_coerce_metadata(document.metadata),
        )

    async def replace_thing_chunks(
        self,
        thing_id: str,
        chunks: list[tuple[str, SearchIndexDocument]],
    ) -> None:
        await self.ensure_schema()
        existing_chunk_ids = set(await self._get_chunk_ids(thing_id))
        next_chunk_ids = [chunk_id for chunk_id, _ in chunks]

        if chunks:
            # Keep the previous index intact until the new documents have been
            # written successfully.
            self._require_embeddings()
            await self._vector_store.aadd_documents(
                [
                    _document_to_langchain_document(chunk_id, document)
                    for chunk_id, document in chunks
                ],
                ids=next_chunk_ids,
            )

        stale_chunk_ids = sorted(existing_chunk_ids.difference(next_chunk_ids))
        if stale_chunk_ids:
            await self._vector_store.adelete(ids=stale_chunk_ids)

    async def delete_thing_chunks(self, thing_id: str) -> None:
        await self.ensure_schema()
        chunk_ids = await self._get_chunk_ids(thing_id)
        if chunk_ids:
            await self._vector_store.adelete(ids=chunk_ids)

    async def _get_chunk_ids(self, thing_id: str) -> list[str]:
        result = await asyncio.to_thread(
            self._vector_store.get,
            where={"id": thing_id},
            include=[],
        )
        ids = result.get("ids", [])
        return [str(chunk_id) for chunk_id in ids if isinstance(chunk_id, str)]

    def _require_embeddings(self) -> None:
        if self._embeddings is None:
            raise RuntimeError(
                "OPENAI_API_KEY must be set for semantic search operations."
            )
