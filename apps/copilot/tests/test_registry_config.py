from copilot.core.config import get_settings


def test_thing_event_outbox_settings_are_configurable(monkeypatch):
    monkeypatch.setenv("THING_EVENT_OUTBOX_BATCH_SIZE", "7")
    monkeypatch.setenv("THING_EVENT_OUTBOX_POLL_INTERVAL_SECONDS", "1.25")
    monkeypatch.setenv("SEARCH_VECTOR_DIMENSIONS", "4")

    get_settings.cache_clear()

    settings = get_settings()

    assert settings.THING_EVENT_OUTBOX_BATCH_SIZE == 7
    assert settings.THING_EVENT_OUTBOX_POLL_INTERVAL_SECONDS == 1.25
    assert settings.SEARCH_VECTOR_DIMENSIONS == 4

    get_settings.cache_clear()


def test_embedding_settings_fall_back_to_openai_settings(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://openai-compatible")
    monkeypatch.setenv("OPENAI_API_BASE_URL", "http://openai-compatible")
    monkeypatch.setenv("OPENAI_API_KEY", "llm-key")
    monkeypatch.setenv("OPENAI_EMBEDDING_API_BASE_URL", "")
    monkeypatch.setenv("OPENAI_EMBEDDING_API_KEY", "")

    get_settings.cache_clear()

    settings = get_settings()

    assert settings.OPENAI_EMBEDDING_API_BASE_URL == "http://openai-compatible"
    assert settings.OPENAI_EMBEDDING_API_KEY == "llm-key"

    get_settings.cache_clear()
