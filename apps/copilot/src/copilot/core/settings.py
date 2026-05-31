import os
import socket

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("OPENAI_BASE_URL", "OPENAI_API_BASE_URL"),
    )

    # Agent
    max_iterations: int = 20
    recursion_limit: int = 50
    max_context_tokens: int = 120000
    parallel_tool_calls: bool = False
    agent_state_database_url: str = ""

    # Security
    internal_api_key: str = ""

    # Browser media ingress
    media_rtc_configuration: str = ""
    media_server_rtc_configuration: str = ""
    media_ice_gather_timeout_ms: int = 750

    # Speech-to-text
    stt_enabled: bool = False
    stt_transcriptions_url: str = ""
    stt_model: str = "whisper-large-turbo"
    stt_api_key: str = ""
    stt_language: str = ""
    stt_timeout_seconds: int = 30
    stt_submit_to_chat: bool = True

    # Voice activity detection
    vad_threshold: float = 0.5
    vad_min_speech_ms: int = 250
    vad_min_silence_ms: int = 700
    vad_speech_pad_ms: int = 200
    vad_max_utterance_ms: int = 20000

    # Vision (look-at-camera)
    vision_enabled: bool = False
    vision_api_base_url: str = ""
    vision_api_key: str = ""
    vision_model: str = ""
    vision_timeout_seconds: int = 30
    vision_max_image_dimension: int = 1024
    vision_jpeg_quality: int = 85

    # Text-to-speech
    tts_enabled: bool = False
    tts_speech_url: str = "http://kokoro-tts:8880/v1/audio/speech"
    tts_model: str = "kokoro"
    tts_voice: str = "af_heart"
    tts_api_key: str = ""
    tts_response_format: str = "pcm"
    tts_speed: float = 1.0
    tts_timeout_seconds: int = 60

    # Code Executor
    code_executor_url: str = "http://localhost:8888"
    code_executor_timeout_seconds: int = 330
    code_executor_retry_attempts: int = 3
    code_executor_retry_backoff_seconds: float = 1.0

    # Jobs
    job_task_timeout_seconds: int = 300
    redis_url: str = "redis://valkey:6379"
    wot_runtime_url: str = "http://wot-runtime:3003"
    wot_runtime_api_token: str = ""
    wot_runtime_stream: str = "wot_runtime_events"
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
