"""Maps a resolved reasoning-effort level to ChatOpenAI kwargs for a backend style."""

from typing import Any

from wotbot.core.settings import ReasoningEffortStyle


def reasoning_effort_kwargs(effort: str, style: ReasoningEffortStyle) -> dict[str, Any]:
    """Build ``ChatOpenAI`` kwargs (constructor or ``.bind()``) for one level.

    "openai" sends the level as the OpenAI/vLLM-standard ``reasoning_effort``
    request field directly. "qwen" instead sets Qwen's own
    ``enable_thinking`` chat-template flag via ``extra_body`` — see
    ``ReasoningEffortStyle`` for why. The literal level ``"none"`` means
    thinking off; every other configured level means on, since Qwen's switch
    is binary and has no graduated effort scale.

    "openrouter" sends OpenRouter's ``reasoning`` object, which is what makes
    it return the reasoning text rather than only billing for it. Its effort
    scale has no "none", so that level disables reasoning instead.
    """
    if style == "qwen":
        return {"extra_body": {"chat_template_kwargs": {"enable_thinking": effort != "none"}}}
    if style == "openrouter":
        reasoning = {"enabled": False} if effort == "none" else {"effort": effort}
        return {"extra_body": {"reasoning": reasoning}}
    return {"reasoning_effort": effort}
