from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = ""

    # MCP / WoT Registry
    wot_registry_url: str = "http://localhost:8000/mcp"
    wot_registry_token: str = ""
    wot_registry_timeout_seconds: int = 30
    wot_registry_sse_read_timeout_seconds: int = 300

    # Agent
    max_iterations: int = 20
    recursion_limit: int = 50
    max_context_tokens: int = 120000
    max_checkpoint_tokens: int = 240000
    parallel_tool_calls: bool = False
    agent_state_db_path: str = "/data/agent_state.db"

    # Security
    internal_api_key: str = ""

    # Code Executor
    code_executor_url: str = "http://localhost:8888"
    code_executor_timeout_seconds: int = 330

    # Logging
    log_level: str = "INFO"
