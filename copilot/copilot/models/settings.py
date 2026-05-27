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

    # Logging
    log_level: str = "INFO"
