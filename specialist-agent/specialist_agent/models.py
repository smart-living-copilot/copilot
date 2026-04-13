"""Configuration and schema models for specialist agent runtime."""

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # LLM defaults
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = ""
    default_temperature: float = 0.2
    default_max_turns: int = 6

    # TD / registry lookup
    wot_registry_api_url: str = "http://wot-registry:8000/api"
    wot_registry_token: str = ""
    max_agents_scan: int = 100

    # Service
    internal_api_key: str = ""
    request_timeout_seconds: int = 45
    log_level: str = "INFO"

    # stdio MCP security: comma-separated executables that may be launched via stdio.
    # Empty string (default) means no restriction — any command is permitted.
    stdio_command_allowlist: str = ""


class AgentSearchResult(BaseModel):
    id: str
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    score: float


class ExecuteRequest(BaseModel):
    query: str = Field(min_length=1)
    thread_id: str | None = None
    preferred_agent_id: str | None = None


class ExecuteResponse(BaseModel):
    agent_id: str
    agent_title: str
    score: float
    tool_calls: int
    answer: str
