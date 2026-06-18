from unittest.mock import patch

from copilot.core.llm import make_llm
from copilot.core.settings import Settings


def test_make_llm_omits_temperature_when_unset():
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-test",
        openai_temperature=None,
    )

    with patch("copilot.core.llm.ChatOpenAI", return_value=object()) as chat_openai:
        make_llm(settings)

    assert "temperature" not in chat_openai.call_args.kwargs


def test_make_llm_disables_streaming_for_tool_calling_by_default():
    settings = Settings(openai_api_key="test-key", openai_model="gpt-test")

    with patch("copilot.core.llm.ChatOpenAI", return_value=object()) as chat_openai:
        make_llm(settings)

    assert chat_openai.call_args.kwargs["disable_streaming"] == "tool_calling"


def test_make_llm_passes_configured_disable_streaming_mode():
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-test",
        openai_disable_streaming=True,
    )

    with patch("copilot.core.llm.ChatOpenAI", return_value=object()) as chat_openai:
        make_llm(settings)

    assert chat_openai.call_args.kwargs["disable_streaming"] is True


def test_settings_accepts_false_disable_streaming_mode_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_DISABLE_STREAMING", "false")

    settings = Settings(openai_api_key="test-key", openai_model="gpt-test")

    assert settings.openai_disable_streaming is False


def test_settings_accepts_true_disable_streaming_mode_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_DISABLE_STREAMING", "true")

    settings = Settings(openai_api_key="test-key", openai_model="gpt-test")

    assert settings.openai_disable_streaming is True


def test_settings_accepts_tool_calling_disable_streaming_mode_from_env(monkeypatch):
    monkeypatch.setenv("OPENAI_DISABLE_STREAMING", "tool_calling")

    settings = Settings(openai_api_key="test-key", openai_model="gpt-test")

    assert settings.openai_disable_streaming == "tool_calling"


def test_settings_treats_empty_temperature_as_provider_default(monkeypatch):
    monkeypatch.setenv("OPENAI_TEMPERATURE", "")

    settings = Settings(_env_file=None, openai_api_key="test-key", openai_model="gpt-test")

    assert settings.openai_temperature is None
    assert settings.llm.openai_temperature is None


def test_make_llm_passes_configured_temperature():
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-test",
        openai_temperature=0,
    )

    with patch("copilot.core.llm.ChatOpenAI", return_value=object()) as chat_openai:
        make_llm(settings)

    assert chat_openai.call_args.kwargs["temperature"] == 0
