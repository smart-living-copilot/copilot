from __future__ import annotations

from dataclasses import dataclass

from copilot.config import Settings


@dataclass(frozen=True)
class SearchIndexerStreamConfig:
    stream: str
    group: str
    consumer: str
    batch_size: int
    poll_block_ms: int
    claim_idle_ms: int
    retry_seconds: int

    @classmethod
    def from_settings(cls, settings: Settings) -> "SearchIndexerStreamConfig":
        return cls(
            stream=settings.THING_EVENTS_STREAM,
            group=settings.SEARCH_INDEXER_EVENTS_GROUP,
            consumer=settings.SEARCH_INDEXER_EVENTS_CONSUMER,
            batch_size=settings.SEARCH_INDEXER_BATCH_SIZE,
            poll_block_ms=settings.SEARCH_INDEXER_POLL_BLOCK_MS,
            claim_idle_ms=settings.SEARCH_INDEXER_CLAIM_IDLE_MS,
            retry_seconds=settings.SEARCH_INDEXER_RETRY_SECONDS,
        )
