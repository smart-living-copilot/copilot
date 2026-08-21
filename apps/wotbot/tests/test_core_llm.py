from unittest.mock import patch

from wotbot.core.llm import make_llm
from wotbot.core.settings import Settings


def test_make_llm_omits_temperature_when_unset():
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-test",
        openai_temperature=None,
    )

    with patch("wotbot.core.llm.ChatOpenAI", return_value=object()) as chat_openai:
        make_llm(settings)

    assert "temperature" not in chat_openai.call_args.kwargs


def test_make_llm_disables_streaming_for_tool_calling_by_default():
    settings = Settings(
        _env_file=None,
        openai_api_key="test-key",
        openai_model="gpt-test",
    )

    with patch("wotbot.core.llm.ChatOpenAI", return_value=object()) as chat_openai:
        make_llm(settings)

    assert chat_openai.call_args.kwargs["disable_streaming"] == "tool_calling"


def test_make_llm_passes_configured_disable_streaming_mode():
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-test",
        openai_disable_streaming=True,
    )

    with patch("wotbot.core.llm.ChatOpenAI", return_value=object()) as chat_openai:
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

    with patch("wotbot.core.llm.ChatOpenAI", return_value=object()) as chat_openai:
        make_llm(settings)

    assert chat_openai.call_args.kwargs["temperature"] == 0


def test_make_llm_omits_reasoning_effort_when_disabled():
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-test",
        reasoning_effort_enabled=False,
        reasoning_effort_default="high",
    )

    with patch("wotbot.core.llm.ChatOpenAI", return_value=object()) as chat_openai:
        make_llm(settings)

    assert "reasoning_effort" not in chat_openai.call_args.kwargs


def test_make_llm_omits_reasoning_effort_when_no_default_set():
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-test",
        reasoning_effort_enabled=True,
    )

    with patch("wotbot.core.llm.ChatOpenAI", return_value=object()) as chat_openai:
        make_llm(settings)

    assert "reasoning_effort" not in chat_openai.call_args.kwargs


def test_make_llm_passes_configured_reasoning_effort_default():
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-test",
        reasoning_effort_enabled=True,
        reasoning_effort_default="high",
    )

    with patch("wotbot.core.llm.ChatOpenAI", return_value=object()) as chat_openai:
        make_llm(settings)

    assert chat_openai.call_args.kwargs["reasoning_effort"] == "high"


def test_make_llm_uses_qwen_style_enable_thinking():
    settings = Settings(
        openai_api_key="test-key",
        openai_model="qwen-test",
        reasoning_effort_enabled=True,
        reasoning_effort_levels="none,high",
        reasoning_effort_default="none",
        reasoning_effort_style="qwen",
    )

    with patch("wotbot.core.llm.ChatOpenAI", return_value=object()) as chat_openai:
        make_llm(settings)

    assert "reasoning_effort" not in chat_openai.call_args.kwargs
    assert chat_openai.call_args.kwargs["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False}
    }


def test_settings_reasoning_effort_defaults_to_openai_style():
    settings = Settings(_env_file=None, openai_api_key="test-key")

    assert settings.reasoning_effort.style == "openai"


def test_settings_reasoning_effort_parses_and_trims_levels():
    settings = Settings(
        openai_api_key="test-key",
        reasoning_effort_enabled=True,
        reasoning_effort_levels=" low, medium ,high ",
        reasoning_effort_default="medium",
    )

    assert settings.reasoning_effort.levels == ("low", "medium", "high")
    assert settings.reasoning_effort.default == "medium"


def test_settings_reasoning_effort_drops_default_outside_levels():
    settings = Settings(
        openai_api_key="test-key",
        reasoning_effort_enabled=True,
        reasoning_effort_levels="low,medium",
        reasoning_effort_default="extreme",
    )

    assert settings.reasoning_effort.default is None


def test_settings_reasoning_effort_defaults_to_disabled():
    settings = Settings(_env_file=None, openai_api_key="test-key")

    assert settings.reasoning_effort.enabled is False
    assert settings.reasoning_effort.levels == ("low", "medium", "high")
    assert settings.reasoning_effort.default is None
