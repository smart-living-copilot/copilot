import os
import socket

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_database_url(value: str) -> str:
    if value.startswith("postgresql+psycopg://"):
        return value.replace("postgresql+psycopg://", "postgresql://", 1)
    return value


def _optional(value: str) -> str | None:
    return value or None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    # LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_temperature: float | None = Field(default=None, ge=0, le=2)
    openai_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_BASE_URL", "OPENAI_API_BASE_URL"),
    )
    openai_embedding_api_base_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "OPENAI_EMBEDDING_API_BASE_URL",
            "OPENAI_API_BASE_URL",
            "OPENAI_BASE_URL",
        ),
    )
    openai_embedding_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_EMBEDDING_API_KEY", "OPENAI_API_KEY"),
    )
    openai_embedding_model: str = "mxbai-embed-large"

    # Agent
    max_iterations: int = 20
    recursion_limit: int = 50
    max_context_tokens: int = 120000
    parallel_tool_calls: bool = False
    agent_state_database_url: str = ""

    # Registry and security
    internal_api_key: str = ""
    init_admin_token: str = ""
    wot_runtime_registry_token: str = ""
    registry_database_url: str = "postgresql://copilot:copilot@localhost:5432/copilot"
    registry_public_url: str = "http://localhost:8000"

    # LiveKit media ingress
    livekit_url: str = ""
    livekit_public_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    livekit_agent_name: str = "smart-living-copilot"
    livekit_room_prefix: str = "copilot"
    livekit_token_ttl_seconds: int = 600

    # Speech-to-text
    stt_transcriptions_url: str = ""
    stt_model: str = "whisper-large-turbo"
    stt_api_key: str = ""
    stt_language: str = ""

    # Vision (look-at-camera)
    vision_enabled: bool = False
    vision_api_base_url: str = ""
    vision_api_key: str = ""
    vision_model: str = ""
    vision_timeout_seconds: int = 30
    vision_max_image_dimension: int = 1024
    vision_jpeg_quality: int = 85

    # Text-to-speech
    tts_speech_url: str = "http://kokoro-tts:8880/v1/audio/speech"
    tts_model: str = "kokoro"
    tts_voice: str = "af_heart"
    tts_api_key: str = ""
    tts_response_format: str = "pcm"
    tts_speed: float = 1.0

    # Code Executor
    code_executor_url: str = "http://localhost:8888"
    code_executor_timeout_seconds: int = 330
    code_executor_retry_attempts: int = 3
    code_executor_retry_backoff_seconds: float = 1.0

    # Search and Thing indexing
    search_vector_dimensions: int = Field(default=1024, gt=0)
    thing_events_stream: str = "thing_events"
    thing_event_outbox_batch_size: int = Field(default=20, gt=0)
    thing_event_outbox_poll_interval_seconds: float = Field(default=0.5, gt=0)
    search_indexer_events_group: str = "thing_search_indexer"
    search_indexer_events_consumer: str = Field(
        default_factory=lambda: f"{socket.gethostname()}-{os.getpid()}"
    )
    search_indexer_poll_block_ms: int = 5000
    search_indexer_batch_size: int = 20
    search_indexer_claim_idle_ms: int = 60000
    search_indexer_retry_seconds: float = 5
    rdf_service_url: str = "http://rdf-service:8124"
    rdf_store_path: str = "/data/rdf"
    rdf_events_group: str = "thing_rdf_indexer"
    rdf_events_consumer: str = Field(
        default_factory=lambda: f"{socket.gethostname()}-{os.getpid()}"
    )
    rdf_events_batch_size: int = 20
    rdf_events_poll_block_ms: int = 5000
    rdf_events_claim_idle_ms: int = 60000
    rdf_events_retry_seconds: float = 5
    rdf_query_timeout_seconds: int = 20
    rdf_federation_proxy_base_url: str = "http://localhost:8124"
    rdf_federation_timeout_seconds: int = 10
    rdf_federation_max_response_bytes: int = 2_000_000
    rdf_federation_allowed_hosts: str = ""
    rdf_federation_allow_private_endpoints: bool = False

    # Jobs and WoT runtime
    job_task_timeout_seconds: int = 300
    job_run_stale_after_seconds: int = 900
    jobs_default_timezone: str = "Europe/Berlin"
    redis_url: str = "redis://valkey:6379"
    wot_runtime_url: str = "http://wot-runtime:3003"
    wot_runtime_api_token: str = ""
    wot_runtime_stream: str = "wot_runtime_events"
    wot_runtime_timeout_seconds: int = 15
    wot_runtime_subscription_timeout_seconds: int = 5
    jobs_events_group: str = "job_runner"
    jobs_events_consumer: str = Field(
        default_factory=lambda: f"{socket.gethostname()}-{os.getpid()}"
    )
    jobs_stream_batch_size: int = 20
    jobs_stream_poll_block_ms: int = 5000
    jobs_stream_claim_idle_ms: int = 60000
    jobs_run_events_stream: str = "jobs_run_events"

    # Logging
    log_level: str = "INFO"

    @field_validator("registry_database_url")
    @classmethod
    def _normalize_registry_database_url(cls, value: str) -> str:
        return _normalize_database_url(value)

    @field_validator("openai_temperature", mode="before")
    @classmethod
    def _empty_temperature_uses_provider_default(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @model_validator(mode="after")
    def _apply_fallback_settings(self) -> "Settings":
        if not self.openai_embedding_api_base_url:
            self.openai_embedding_api_base_url = self.openai_base_url
        if not self.openai_embedding_api_key:
            self.openai_embedding_api_key = self.openai_api_key
        return self

    def validate_runtime_security_settings(self) -> None:
        missing: list[str] = []
        if not self.wot_runtime_registry_token:
            missing.append("WOT_RUNTIME_REGISTRY_TOKEN")
        if not self.wot_runtime_api_token:
            missing.append("WOT_RUNTIME_API_TOKEN")

        if missing:
            missing_values = ", ".join(missing)
            raise RuntimeError(
                "WoT runtime integration requires shared auth token(s). "
                f"Missing required setting(s): {missing_values}."
            )

    @property
    def DATABASE_URL(self) -> str:
        return self.registry_database_url

    @property
    def REDIS_URL(self) -> str:
        return self.redis_url

    @property
    def THING_EVENTS_STREAM(self) -> str:
        return self.thing_events_stream

    @property
    def THING_EVENT_OUTBOX_BATCH_SIZE(self) -> int:
        return self.thing_event_outbox_batch_size

    @property
    def THING_EVENT_OUTBOX_POLL_INTERVAL_SECONDS(self) -> float:
        return self.thing_event_outbox_poll_interval_seconds

    @property
    def INIT_ADMIN_TOKEN(self) -> str | None:
        return _optional(self.init_admin_token)

    @property
    def WOT_RUNTIME_REGISTRY_TOKEN(self) -> str | None:
        return _optional(self.wot_runtime_registry_token)

    @property
    def WOT_RUNTIME_API_TOKEN(self) -> str | None:
        return _optional(self.wot_runtime_api_token)

    @property
    def SEARCH_VECTOR_DIMENSIONS(self) -> int:
        return self.search_vector_dimensions

    @property
    def SEARCH_INDEXER_EVENTS_GROUP(self) -> str:
        return self.search_indexer_events_group

    @property
    def SEARCH_INDEXER_EVENTS_CONSUMER(self) -> str:
        return self.search_indexer_events_consumer

    @property
    def SEARCH_INDEXER_POLL_BLOCK_MS(self) -> int:
        return self.search_indexer_poll_block_ms

    @property
    def SEARCH_INDEXER_BATCH_SIZE(self) -> int:
        return self.search_indexer_batch_size

    @property
    def SEARCH_INDEXER_CLAIM_IDLE_MS(self) -> int:
        return self.search_indexer_claim_idle_ms

    @property
    def SEARCH_INDEXER_RETRY_SECONDS(self) -> float:
        return self.search_indexer_retry_seconds

    @property
    def RDF_SERVICE_URL(self) -> str:
        return self.rdf_service_url

    @property
    def RDF_STORE_PATH(self) -> str:
        return self.rdf_store_path

    @property
    def RDF_EVENTS_GROUP(self) -> str:
        return self.rdf_events_group

    @property
    def RDF_EVENTS_CONSUMER(self) -> str:
        return self.rdf_events_consumer

    @property
    def RDF_EVENTS_BATCH_SIZE(self) -> int:
        return self.rdf_events_batch_size

    @property
    def RDF_EVENTS_POLL_BLOCK_MS(self) -> int:
        return self.rdf_events_poll_block_ms

    @property
    def RDF_EVENTS_CLAIM_IDLE_MS(self) -> int:
        return self.rdf_events_claim_idle_ms

    @property
    def RDF_EVENTS_RETRY_SECONDS(self) -> float:
        return self.rdf_events_retry_seconds

    @property
    def RDF_QUERY_TIMEOUT_SECONDS(self) -> int:
        return self.rdf_query_timeout_seconds

    @property
    def RDF_FEDERATION_PROXY_BASE_URL(self) -> str:
        return self.rdf_federation_proxy_base_url

    @property
    def RDF_FEDERATION_TIMEOUT_SECONDS(self) -> int:
        return self.rdf_federation_timeout_seconds

    @property
    def RDF_FEDERATION_MAX_RESPONSE_BYTES(self) -> int:
        return self.rdf_federation_max_response_bytes

    @property
    def RDF_FEDERATION_ALLOWED_HOSTS(self) -> str:
        return self.rdf_federation_allowed_hosts

    @property
    def RDF_FEDERATION_ALLOW_PRIVATE_ENDPOINTS(self) -> bool:
        return self.rdf_federation_allow_private_endpoints

    @property
    def OPENAI_API_BASE_URL(self) -> str | None:
        return _optional(self.openai_base_url)

    @property
    def OPENAI_API_KEY(self) -> str | None:
        return _optional(self.openai_api_key)

    @property
    def OPENAI_MODEL(self) -> str | None:
        return _optional(self.openai_model)

    @property
    def OPENAI_TEMPERATURE(self) -> float | None:
        return self.openai_temperature

    @property
    def OPENAI_EMBEDDING_API_BASE_URL(self) -> str | None:
        return _optional(self.openai_embedding_api_base_url)

    @property
    def OPENAI_EMBEDDING_API_KEY(self) -> str | None:
        return _optional(self.openai_embedding_api_key)

    @property
    def OPENAI_EMBEDDING_MODEL(self) -> str:
        return self.openai_embedding_model

    @property
    def WOT_RUNTIME_URL(self) -> str:
        return self.wot_runtime_url

    @property
    def WOT_RUNTIME_TIMEOUT_SECONDS(self) -> int:
        return self.wot_runtime_timeout_seconds

    @property
    def WOT_RUNTIME_SUBSCRIPTION_TIMEOUT_SECONDS(self) -> int:
        return self.wot_runtime_subscription_timeout_seconds

    @property
    def REGISTRY_PUBLIC_URL(self) -> str:
        return self.registry_public_url
