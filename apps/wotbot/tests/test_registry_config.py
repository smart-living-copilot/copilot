import pytest

from wotbot.core.config import get_settings
from wotbot.core.settings import Settings


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


def test_grouped_settings_mirror_flat_fields():
    settings = Settings(
        _env_file=None,
        openai_api_key="llm-key",
        openai_model="gpt-test",
        openai_base_url="http://openai-compatible",
        openai_embedding_api_base_url="",
        openai_embedding_api_key="",
        registry_database_url="postgresql+psycopg://wotbot:wotbot@postgres:5432/wotbot",
        redis_url="redis://test-redis:6379",
        rdf_store_path="/tmp/rdf",
        wot_runtime_registry_token="registry-token",
        virtual_servient_registry_token="",
        search_vector_dimensions=4,
        log_level="DEBUG",
    )

    assert settings.llm.openai_model == settings.openai_model
    assert settings.llm.openai_api_key == settings.openai_api_key
    assert settings.embeddings.api_base_url == settings.openai_base_url
    assert settings.embeddings.api_key == settings.openai_api_key
    assert settings.registry.database_url == settings.registry_database_url
    assert settings.registry.database_url.startswith("postgresql://")
    assert settings.indexing.search_vector_dimensions == settings.search_vector_dimensions
    assert settings.rdf.store_path == settings.rdf_store_path
    assert settings.jobs.redis_url == settings.redis_url
    assert settings.wot_runtime.virtual_servient_registry_token == "registry-token"
    assert settings.logging.level == settings.log_level


def test_openai_api_base_url_aliases_are_preserved(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_BASE_URL", "http://legacy-openai-compatible")

    settings = Settings(_env_file=None)

    assert settings.openai_base_url == "http://legacy-openai-compatible"
    assert settings.llm.openai_base_url == "http://legacy-openai-compatible"


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
    assert settings.embeddings.api_base_url == "http://openai-compatible"
    assert settings.embeddings.api_key == "llm-key"

    get_settings.cache_clear()


def test_uppercase_compatibility_properties_match_grouped_values():
    settings = Settings(
        _env_file=None,
        openai_api_key="llm-key",
        openai_model="gpt-test",
        openai_base_url="http://openai-compatible",
        openai_embedding_model="embed-test",
        registry_database_url="postgresql://wotbot:wotbot@postgres:5432/wotbot",
        rdf_store_path="/tmp/rdf",
        wot_runtime_url="http://wot-runtime:3003",
    )

    assert settings.OPENAI_API_KEY == settings.llm.openai_api_key
    assert settings.OPENAI_MODEL == settings.llm.openai_model
    assert settings.OPENAI_API_BASE_URL == settings.llm.openai_base_url
    assert settings.OPENAI_EMBEDDING_MODEL == settings.embeddings.model
    assert settings.DATABASE_URL == settings.registry.database_url
    assert settings.RDF_STORE_PATH == settings.rdf.store_path
    assert settings.WOT_RUNTIME_URL == settings.wot_runtime.url


def test_runtime_security_validation_error_names_are_unchanged():
    settings = Settings(
        _env_file=None,
        wot_runtime_registry_token="",
        wot_runtime_api_token="",
    )

    with pytest.raises(RuntimeError, match="WOT_RUNTIME_REGISTRY_TOKEN, WOT_RUNTIME_API_TOKEN"):
        settings.validate_runtime_security_settings()


def test_openai_temperature_is_configurable(monkeypatch):
    monkeypatch.setenv("OPENAI_TEMPERATURE", "0")

    get_settings.cache_clear()

    settings = get_settings()

    assert settings.OPENAI_TEMPERATURE == 0

    get_settings.cache_clear()
