import os
import socket
from dataclasses import dataclass
from functools import lru_cache


def _normalize_database_url(value: str) -> str:
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    DATABASE_URL: str
    REDIS_URL: str
    THING_EVENTS_STREAM: str
    INIT_ADMIN_TOKEN: str | None
    WOT_RUNTIME_REGISTRY_TOKEN: str | None
    WOT_RUNTIME_API_TOKEN: str | None
    SEARCH_VECTOR_COLLECTION_NAME: str
    SEARCH_VECTOR_STORE_DIR: str
    SEARCH_INDEXER_EVENTS_GROUP: str
    SEARCH_INDEXER_EVENTS_CONSUMER: str
    SEARCH_INDEXER_POLL_BLOCK_MS: int
    SEARCH_INDEXER_BATCH_SIZE: int
    SEARCH_INDEXER_CLAIM_IDLE_MS: int
    SEARCH_INDEXER_RETRY_SECONDS: float
    OPENAI_API_BASE_URL: str | None
    OPENAI_API_KEY: str | None
    OPENAI_MODEL: str | None
    OPENAI_EMBEDDING_API_BASE_URL: str | None
    OPENAI_EMBEDDING_API_KEY: str | None
    OPENAI_EMBEDDING_MODEL: str
    WOT_RUNTIME_URL: str
    WOT_RUNTIME_TIMEOUT_SECONDS: int
    WOT_RUNTIME_SUBSCRIPTION_TIMEOUT_SECONDS: int
    REGISTRY_PUBLIC_URL: str

    def validate_search_settings(self) -> None:
        missing: list[str] = []
        if not self.OPENAI_API_KEY:
            missing.append("OPENAI_API_KEY")
        if not self.OPENAI_MODEL:
            missing.append("OPENAI_MODEL")

        if missing:
            missing_values = ", ".join(missing)
            raise RuntimeError(
                "Semantic search indexing is always enabled. "
                f"Missing required setting(s): {missing_values}."
            )

    def validate_runtime_security_settings(self) -> None:
        missing: list[str] = []
        if not self.WOT_RUNTIME_REGISTRY_TOKEN:
            missing.append("WOT_RUNTIME_REGISTRY_TOKEN")
        if not self.WOT_RUNTIME_API_TOKEN:
            missing.append("WOT_RUNTIME_API_TOKEN")

        if missing:
            missing_values = ", ".join(missing)
            raise RuntimeError(
                "WoT runtime integration requires shared auth token(s). "
                f"Missing required setting(s): {missing_values}."
            )


@lru_cache()
def get_settings() -> Settings:
    database_url = os.getenv("REGISTRY_DATABASE_URL", "sqlite:///./wot_registry.db")

    return Settings(
        DATABASE_URL=_normalize_database_url(database_url),
        REDIS_URL=os.getenv("REDIS_URL", "redis://valkey:6379"),
        THING_EVENTS_STREAM=os.getenv("THING_EVENTS_STREAM", "thing_events"),
        INIT_ADMIN_TOKEN=os.getenv("INIT_ADMIN_TOKEN") or None,
        WOT_RUNTIME_REGISTRY_TOKEN=os.getenv("WOT_RUNTIME_REGISTRY_TOKEN") or None,
        WOT_RUNTIME_API_TOKEN=os.getenv("WOT_RUNTIME_API_TOKEN") or None,
        SEARCH_VECTOR_COLLECTION_NAME=os.getenv(
            "SEARCH_VECTOR_COLLECTION_NAME",
            "thing_search",
        ),
        SEARCH_VECTOR_STORE_DIR=os.getenv(
            "SEARCH_VECTOR_STORE_DIR",
            "./data/search-index",
        ),
        SEARCH_INDEXER_EVENTS_GROUP=os.getenv(
            "SEARCH_INDEXER_EVENTS_GROUP", "thing_search_indexer"
        ),
        SEARCH_INDEXER_EVENTS_CONSUMER=os.getenv(
            "SEARCH_INDEXER_EVENTS_CONSUMER",
            f"{socket.gethostname()}-{os.getpid()}",
        ),
        SEARCH_INDEXER_POLL_BLOCK_MS=_int_env("SEARCH_INDEXER_POLL_BLOCK_MS", 5000),
        SEARCH_INDEXER_BATCH_SIZE=_int_env("SEARCH_INDEXER_BATCH_SIZE", 20),
        SEARCH_INDEXER_CLAIM_IDLE_MS=_int_env("SEARCH_INDEXER_CLAIM_IDLE_MS", 60000),
        SEARCH_INDEXER_RETRY_SECONDS=float(
            os.getenv("SEARCH_INDEXER_RETRY_SECONDS", "5")
        ),
        OPENAI_API_BASE_URL=os.getenv("OPENAI_API_BASE_URL") or None,
        OPENAI_API_KEY=os.getenv("OPENAI_API_KEY") or None,
        OPENAI_MODEL=os.getenv("OPENAI_MODEL") or None,
        OPENAI_EMBEDDING_API_BASE_URL=os.getenv("OPENAI_EMBEDDING_API_BASE_URL")
        or os.getenv("OPENAI_API_BASE_URL")
        or None,
        OPENAI_EMBEDDING_API_KEY=os.getenv("OPENAI_EMBEDDING_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or None,
        OPENAI_EMBEDDING_MODEL=os.getenv("OPENAI_EMBEDDING_MODEL", "mxbai-embed-large"),
        WOT_RUNTIME_URL=os.getenv("WOT_RUNTIME_URL", "http://localhost:3003"),
        WOT_RUNTIME_TIMEOUT_SECONDS=_int_env("WOT_RUNTIME_TIMEOUT_SECONDS", 15),
        WOT_RUNTIME_SUBSCRIPTION_TIMEOUT_SECONDS=_int_env(
            "WOT_RUNTIME_SUBSCRIPTION_TIMEOUT_SECONDS",
            5,
        ),
        REGISTRY_PUBLIC_URL=os.getenv("REGISTRY_PUBLIC_URL", "http://localhost:8000"),
    )
