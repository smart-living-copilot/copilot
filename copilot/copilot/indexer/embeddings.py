from __future__ import annotations

from langchain_core.embeddings import Embeddings
from openai import AsyncOpenAI, OpenAI


def create_openai_client(
    *,
    base_url: str | None,
    api_key: str | None,
) -> AsyncOpenAI:
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY must be set for semantic search features.")
    return AsyncOpenAI(base_url=base_url, api_key=api_key)


def _normalize_text(value: str) -> str:
    return value.replace("\n", " ")


class OpenAIEmbeddingsAdapter(Embeddings):
    def __init__(
        self,
        *,
        model: str,
        base_url: str | None,
        api_key: str | None,
    ) -> None:
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY must be set for semantic search features."
            )
        self._model = model
        self._sync_client = OpenAI(base_url=base_url, api_key=api_key)
        self._async_client = AsyncOpenAI(base_url=base_url, api_key=api_key)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._sync_client.embeddings.create(
            input=[_normalize_text(text) for text in texts],
            model=self._model,
            encoding_format="float",
        )
        return [data.embedding for data in response.data]

    def embed_query(self, text: str) -> list[float]:
        response = self._sync_client.embeddings.create(
            input=[_normalize_text(text)],
            model=self._model,
            encoding_format="float",
        )
        return response.data[0].embedding

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._async_client.embeddings.create(
            input=[_normalize_text(text) for text in texts],
            model=self._model,
            encoding_format="float",
        )
        return [data.embedding for data in response.data]

    async def aembed_query(self, text: str) -> list[float]:
        response = await self._async_client.embeddings.create(
            input=[_normalize_text(text)],
            model=self._model,
            encoding_format="float",
        )
        return response.data[0].embedding

    async def close(self) -> None:
        sync_close = getattr(self._sync_client, "close", None)
        if callable(sync_close):
            sync_close()

        async_close = getattr(self._async_client, "close", None)
        if callable(async_close):
            await async_close()


def create_openai_embeddings(
    *,
    base_url: str | None,
    api_key: str | None,
    model: str,
) -> OpenAIEmbeddingsAdapter:
    return OpenAIEmbeddingsAdapter(
        model=model,
        base_url=base_url,
        api_key=api_key,
    )
