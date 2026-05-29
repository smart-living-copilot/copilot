"""Vision tool: snapshot the live camera and describe what's in frame."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, SecretStr

from copilot.media import media_sessions
from copilot.core.settings import Settings

logger = logging.getLogger(__name__)

_settings = Settings()

_VISION_SYSTEM_PROMPT = """\
You are the visual perception module of a smart-home assistant. You will be \
shown a single frame captured from the user's live camera feed. Identify the \
most relevant controllable object the user is likely referring to, and the \
room/scene context.

Respond strictly in the requested JSON shape:
- primary_object: the single object the camera appears to be aimed at \
  (e.g. "table lamp", "OLED TV", "thermostat"). Use null if no recognizable \
  device is in frame.
- candidates: up to three plausible alternatives (other devices visible).
- scene: the room or scene type (e.g. "living room", "kitchen counter", \
  "bedroom"). Use null if not determinable.
- confidence: "high", "medium", or "low".
- notes: one short sentence with anything else worth knowing \
  (e.g. "the device is powered on", "the camera is partially obscured").

Be conservative: prefer null over guessing. Never invent brand or model names \
you can't actually see.\
"""


class CameraObservation(BaseModel):
    primary_object: str | None = Field(
        default=None,
        description="Most likely device the camera is aimed at, or null.",
    )
    candidates: list[str] = Field(
        default_factory=list,
        description="Up to three other visible devices.",
    )
    scene: str | None = Field(
        default=None,
        description="Room/scene type, or null.",
    )
    confidence: str = Field(default="low", description="high | medium | low")
    notes: str = Field(default="", description="Short additional context.")


def _make_vision_llm() -> ChatOpenAI:
    base_url = _settings.vision_api_base_url or _settings.openai_base_url
    api_key = _settings.vision_api_key or _settings.openai_api_key
    model = _settings.vision_model or _settings.openai_model
    return ChatOpenAI(
        model=model,
        api_key=SecretStr(api_key) if api_key else None,
        base_url=base_url or None,
        timeout=_settings.vision_timeout_seconds,
        max_retries=1,
    )


def _frame_to_message(jpeg_bytes: bytes, user_hint: str | None) -> HumanMessage:
    image_b64 = base64.b64encode(jpeg_bytes).decode("ascii")
    text = (
        "Describe the device the camera is pointed at and the scene around it."
        if not user_hint
        else f"User context: {user_hint}\n\nDescribe what you see."
    )
    return HumanMessage(
        content=[
            {"type": "text", "text": text},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
            },
        ]
    )


@tool
async def look_at_camera(
    user_hint: str | None = None,
    *,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Capture the latest frame from the user's live camera and describe it.

    Use this tool whenever the user says things like "this", "that one",
    "point at", "what is this", or otherwise refers to something they're
    showing rather than naming. Also use it when you need room context for
    disambiguation (e.g. "what's the temperature" without a room).

    Optional ``user_hint``: a short sentence with the user's intent
    ("turn this off", "what can this do") so the vision model knows what to
    focus on.

    Returns: { primary_object, candidates, scene, confidence, notes,
    captured_at }. Returns { error } if vision is disabled or no live
    frame is available.
    """
    if not _settings.vision_enabled:
        return {"error": "Vision is disabled. Set VISION_ENABLED=true to use it."}
    if not _settings.vision_model:
        return {"error": "VISION_MODEL is not configured."}

    thread_id = config.get("configurable", {}).get("thread_id")
    if not thread_id:
        return {"error": "No thread_id in context; cannot locate camera session."}

    snapshot = media_sessions.latest_video_frame_for_thread(thread_id)
    if snapshot is None:
        return {
            "error": (
                "The camera is not active right now. This tool only works while "
                "the user has a live camera feed on. Ask them to turn the camera "
                "on, then try again — and do not guess what they're looking at."
            )
        }
    jpeg_bytes, captured_at = snapshot

    llm = _make_vision_llm().with_structured_output(CameraObservation)
    try:
        raw = await llm.ainvoke(
            [
                SystemMessage(content=_VISION_SYSTEM_PROMPT),
                _frame_to_message(jpeg_bytes, user_hint),
            ]
        )
    except Exception as exc:
        logger.exception("Vision model call failed")
        return {"error": f"Vision model call failed: {exc}"}

    observation = cast(CameraObservation, raw)
    result = json.loads(observation.model_dump_json())
    result["captured_at"] = captured_at
    return result
