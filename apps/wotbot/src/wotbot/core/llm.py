"""Helpers for creating the wotbot LLM."""

import logging
from typing import Any

from langchain_openai import ChatOpenAI

from wotbot.core.settings import Settings

logger = logging.getLogger(__name__)


def make_llm(settings: Settings) -> ChatOpenAI:
    llm = settings.llm
    kwargs: dict[str, Any] = {
        "model": llm.openai_model,
        "api_key": llm.openai_api_key,
        "base_url": llm.openai_base_url or None,
        "disable_streaming": llm.openai_disable_streaming,
        "timeout": 120,
        "max_retries": 2,
    }
    if llm.openai_temperature is not None:
        kwargs["temperature"] = llm.openai_temperature
    reasoning_effort = settings.reasoning_effort
    if reasoning_effort.enabled and reasoning_effort.default:
        kwargs["reasoning_effort"] = reasoning_effort.default
    return ChatOpenAI(**kwargs)
