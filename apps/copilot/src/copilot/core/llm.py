"""Helpers for creating the copilot LLM."""

import logging
from typing import Any

from langchain_openai import ChatOpenAI

from copilot.core.settings import Settings

logger = logging.getLogger(__name__)


def make_llm(settings: Settings) -> ChatOpenAI:
    kwargs: dict[str, Any] = {
        "model": settings.openai_model,
        "api_key": settings.openai_api_key,
        "base_url": settings.openai_base_url or None,
        "disable_streaming": settings.openai_disable_streaming,
        "timeout": 120,
        "max_retries": 2,
    }
    if settings.openai_temperature is not None:
        kwargs["temperature"] = settings.openai_temperature
    return ChatOpenAI(**kwargs)
