from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    idle_timeout_seconds: int = 1800
    execution_timeout_seconds: int = 300
    max_sessions: int = 50
    log_level: str = "INFO"
    artifacts_dir: str = "/tmp/code-executor-artifacts"
    artifacts_ttl_seconds: int = 3600

    # Security
    internal_api_key: str = ""

    # WoT registry access for sandbox WoT client
    wot_registry_url: str = "http://copilot:8123"
    wot_registry_token: str = Field(
        default="",
        validation_alias=AliasChoices("WOT_REGISTRY_TOKEN", "INIT_ADMIN_TOKEN"),
    )
