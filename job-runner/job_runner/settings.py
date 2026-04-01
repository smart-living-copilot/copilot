from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    log_level: str = "INFO"
    jobs_db_path: str = "/data/jobs.db"
    scheduler_poll_seconds: int = 2

    redis_url: str = "redis://valkey:6379"
    wot_runtime_stream: str = "wot_runtime_events"
    jobs_events_group: str = "job_runner"
    jobs_events_consumer: str = "job_runner_1"
    jobs_stream_batch_size: int = 20
    jobs_stream_poll_block_ms: int = 5000
    jobs_stream_claim_idle_ms: int = 60000

    wot_runtime_url: str = "http://wot-runtime:3003"
    wot_runtime_api_token: str = ""

    copilot_url: str = "http://copilot:8123"
    internal_api_key: str = ""
    copilot_timeout_seconds: int = 120
