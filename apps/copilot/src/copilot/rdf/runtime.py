from __future__ import annotations

from dataclasses import dataclass

from copilot.core.config import Settings


@dataclass(frozen=True)
class RdfStreamConfig:
    stream: str
    group: str
    consumer: str
    batch_size: int
    poll_block_ms: int
    claim_idle_ms: int
    retry_seconds: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "RdfStreamConfig":
        return cls(
            stream=settings.THING_EVENTS_STREAM,
            group=settings.RDF_EVENTS_GROUP,
            consumer=settings.RDF_EVENTS_CONSUMER,
            batch_size=settings.RDF_EVENTS_BATCH_SIZE,
            poll_block_ms=settings.RDF_EVENTS_POLL_BLOCK_MS,
            claim_idle_ms=settings.RDF_EVENTS_CLAIM_IDLE_MS,
            retry_seconds=settings.RDF_EVENTS_RETRY_SECONDS,
        )
