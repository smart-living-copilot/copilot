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
