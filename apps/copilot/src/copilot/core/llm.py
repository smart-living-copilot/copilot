"""Helpers for creating the copilot LLM."""

import logging

from langchain_openai import ChatOpenAI

from copilot.core.settings import Settings

logger = logging.getLogger(__name__)


def make_llm(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        timeout=120,
        max_retries=2,
    )
