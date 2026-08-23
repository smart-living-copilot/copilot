"""A ChatOpenAI subclass that keeps OpenRouter's reasoning text.

``langchain-openai`` parses the OpenAI schema only and, by its own
documentation, drops "non-standard response fields added by third-party
providers (e.g. ``reasoning_content``, ``reasoning_details``)", pointing at a
provider-specific subclass as the supported way to keep them. This is that
subclass.

Without it the reasoning is billed and thrown away: OpenRouter reports the
spend in ``output_token_details.reasoning`` while the text never reaches the
message. Note the request side matters too -- a plain ``reasoning_effort``
makes OpenRouter return the ``reasoning`` field empty, so
``ReasoningEffortStyle`` must be ``"openrouter"`` for there to be anything to
extract here (see ``reasoning_effort_kwargs``).

The text is lifted into ``additional_kwargs["reasoning"]`` rather than turned
into a content block: ``content`` is fed back to the model on the next turn,
and a block type the provider never emits itself does not belong in that round
trip. The UI turns this key into a reasoning part at the display boundary.
"""

from typing import Any

from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI

REASONING_KEY = "reasoning"


def _reasoning_text(payload: Any) -> str | None:
    """Pull reasoning text out of one message or streaming delta."""
    if not isinstance(payload, dict):
        return None

    text = payload.get(REASONING_KEY)
    if isinstance(text, str) and text:
        return text
    return None


class ChatOpenRouter(ChatOpenAI):
    """ChatOpenAI that preserves OpenRouter's ``reasoning`` field."""

    def _create_chat_result(
        self,
        response: Any,
        generation_info: dict | None = None,
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)

        raw = response if isinstance(response, dict) else getattr(response, "model_dump", dict)()
        if not isinstance(raw, dict):
            return result

        for generation, choice in zip(result.generations, raw.get("choices") or [], strict=False):
            text = _reasoning_text((choice or {}).get("message"))
            if text:
                generation.message.additional_kwargs[REASONING_KEY] = text

        return result

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if generation_chunk is None:
            return None

        choices = chunk.get("choices") or chunk.get("chunk", {}).get("choices") or []
        for choice in choices:
            text = _reasoning_text((choice or {}).get("delta"))
            if text:
                # Message chunks merge by concatenating string kwargs, so each
                # delta appends and the finished message carries the whole trace.
                generation_chunk.message.additional_kwargs[REASONING_KEY] = text
                break

        return generation_chunk
