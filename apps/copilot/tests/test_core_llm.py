from unittest.mock import patch

from copilot.core.llm import make_llm
from copilot.core.settings import Settings


def test_make_llm_omits_temperature_when_unset():
    settings = Settings(openai_api_key="test-key", openai_model="gpt-test")

    with patch("copilot.core.llm.ChatOpenAI", return_value=object()) as chat_openai:
        make_llm(settings)

    assert "temperature" not in chat_openai.call_args.kwargs


def test_make_llm_passes_configured_temperature():
    settings = Settings(
        openai_api_key="test-key",
        openai_model="gpt-test",
        openai_temperature=0,
    )

    with patch("copilot.core.llm.ChatOpenAI", return_value=object()) as chat_openai:
        make_llm(settings)

    assert chat_openai.call_args.kwargs["temperature"] == 0
