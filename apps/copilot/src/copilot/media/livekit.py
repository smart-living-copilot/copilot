"""LiveKit helpers for browser media sessions."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import timedelta
from typing import Any


_SAFE_LIVEKIT_NAME = re.compile(r"[^A-Za-z0-9_-]+")
_MAX_ROOM_COMPONENT_LENGTH = 80


@dataclass(frozen=True)
class LiveKitConnectionDetails:
    url: str
    token: str
    room: str
    participant_identity: str
    agent_name: str
    metadata: str
    expires_in_seconds: int

    def as_response(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "url": self.url,
            "token": self.token,
            "room": self.room,
            "participantIdentity": self.participant_identity,
            "agentName": self.agent_name,
            "expiresInSeconds": self.expires_in_seconds,
        }


class LiveKitAgentDispatchError(RuntimeError):
    """Raised when the self-hosted LiveKit agent cannot be assigned to a room."""


def is_livekit_configured(settings: Any | None) -> bool:
    return bool(
        settings
        and str(getattr(settings, "livekit_url", "")).strip()
        and str(getattr(settings, "livekit_api_key", "")).strip()
        and str(getattr(settings, "livekit_api_secret", "")).strip()
    )


def _safe_livekit_name_component(value: str, *, fallback: str) -> str:
    cleaned = _SAFE_LIVEKIT_NAME.sub("-", value.strip()).strip("-_")
    if not cleaned:
        cleaned = fallback
    if len(cleaned) <= _MAX_ROOM_COMPONENT_LENGTH:
        return cleaned

    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{cleaned[:_MAX_ROOM_COMPONENT_LENGTH - 17]}-{digest}"


def livekit_room_name(
    settings: Any,
    thread_id: str | None,
    *,
    session_id: str | None = None,
) -> str:
    prefix = _safe_livekit_name_component(
        str(getattr(settings, "livekit_room_prefix", "copilot")),
        fallback="copilot",
    )
    live_session_id = session_id or str(uuid.uuid4())
    suffix_source = f"{thread_id or 'session'}-{live_session_id}"
    suffix = _safe_livekit_name_component(suffix_source, fallback=f"session-{live_session_id}")
    return f"{prefix}-{suffix}"


def is_expected_livekit_room(settings: Any, room: str) -> bool:
    prefix = _safe_livekit_name_component(
        str(getattr(settings, "livekit_room_prefix", "copilot")),
        fallback="copilot",
    )
    return room.startswith(f"{prefix}-")


def livekit_session_metadata(
    *,
    thread_id: str | None,
    room: str,
    participant_identity: str = "",
) -> str:
    return json.dumps(
        {
            "threadId": thread_id or "",
            "room": room,
            "participantIdentity": participant_identity,
        },
        separators=(",", ":"),
    )


def _load_livekit_api_module():
    try:
        from livekit import api
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on optional package.
        raise RuntimeError(
            "LiveKit token generation requires the livekit-agents package to be installed"
        ) from exc
    return api


def create_livekit_connection_details(
    settings: Any,
    *,
    thread_id: str | None,
    api_module: Any | None = None,
) -> LiveKitConnectionDetails:
    if not is_livekit_configured(settings):
        raise ValueError("LiveKit is not configured")

    api = api_module or _load_livekit_api_module()
    ttl_seconds = max(60, int(getattr(settings, "livekit_token_ttl_seconds", 600)))
    agent_name = str(getattr(settings, "livekit_agent_name", "smart-living-copilot")).strip()
    participant_identity = f"web-{uuid.uuid4()}"
    room = livekit_room_name(settings, thread_id)
    metadata = livekit_session_metadata(
        thread_id=thread_id,
        room=room,
        participant_identity=participant_identity,
    )
    attributes = {"threadId": thread_id or ""}

    token = (
        api.AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_ttl(timedelta(seconds=ttl_seconds))
        .with_identity(participant_identity)
        .with_name("Smart Living Copilot user")
        .with_metadata(metadata)
        .with_attributes(attributes)
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
                can_update_own_metadata=True,
            )
        )
    )

    return LiveKitConnectionDetails(
        url=settings.livekit_public_url or settings.livekit_url,
        token=token.to_jwt(),
        room=room,
        participant_identity=participant_identity,
        agent_name=agent_name,
        metadata=metadata,
        expires_in_seconds=ttl_seconds,
    )


def _dispatch_job_status(api: Any, dispatch: Any) -> str:
    status_field = (
        api.AgentDispatchState.DESCRIPTOR.fields_by_name["jobs"]
        .message_type.fields_by_name["state"]
        .message_type.fields_by_name["status"]
    )
    enum_type = status_field.enum_type
    jobs = getattr(getattr(dispatch, "state", None), "jobs", [])
    statuses = []
    for job in jobs:
        status = getattr(getattr(job, "state", None), "status", None)
        if isinstance(status, int):
            statuses.append(enum_type.values_by_number[status].name)
    return ",".join(statuses)


def _dispatch_job_is_running(api: Any, dispatch: Any) -> bool:
    return "JS_RUNNING" in _dispatch_job_status(api, dispatch).split(",")


def _dispatch_job_failed(api: Any, dispatch: Any) -> str | None:
    status_field = (
        api.AgentDispatchState.DESCRIPTOR.fields_by_name["jobs"]
        .message_type.fields_by_name["state"]
        .message_type.fields_by_name["status"]
    )
    enum_type = status_field.enum_type
    jobs = getattr(getattr(dispatch, "state", None), "jobs", [])
    for job in jobs:
        state = getattr(job, "state", None)
        status = getattr(state, "status", None)
        if isinstance(status, int) and enum_type.values_by_number[status].name == "JS_FAILED":
            return getattr(state, "error", "") or "agent job failed"
    return None


async def dispatch_livekit_agent(
    settings: Any,
    *,
    room: str,
    thread_id: str | None,
    participant_identity: str = "",
    api_module: Any | None = None,
    timeout_seconds: float = 15.0,
    poll_interval_seconds: float = 0.25,
) -> None:
    if not is_livekit_configured(settings):
        raise ValueError("LiveKit is not configured")
    if not room or not is_expected_livekit_room(settings, room):
        raise ValueError("LiveKit room is invalid")

    agent_name = str(getattr(settings, "livekit_agent_name", "smart-living-copilot")).strip()
    if not agent_name:
        raise ValueError("LiveKit agent name is not configured")

    api = api_module or _load_livekit_api_module()
    metadata = livekit_session_metadata(
        thread_id=thread_id,
        room=room,
        participant_identity=participant_identity,
    )
    client = api.LiveKitAPI(
        settings.livekit_url,
        settings.livekit_api_key,
        settings.livekit_api_secret,
    )

    dispatch_id = ""
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    last_error: Exception | None = None
    try:
        try:
            while True:
                try:
                    if not dispatch_id:
                        dispatch = await client.agent_dispatch.create_dispatch(
                            api.CreateAgentDispatchRequest(
                                room=room,
                                agent_name=agent_name,
                                metadata=metadata,
                            )
                        )
                        dispatch_id = getattr(dispatch, "id", "")

                    dispatches = await client.agent_dispatch.list_dispatch(room)
                    matching_dispatches = [
                        item
                        for item in dispatches
                        if getattr(item, "id", "") == dispatch_id
                        or (
                            not dispatch_id
                            and getattr(item, "agent_name", "") == agent_name
                            and getattr(item, "metadata", "") == metadata
                        )
                    ]
                    for item in matching_dispatches:
                        if _dispatch_job_is_running(api, item):
                            return
                        error = _dispatch_job_failed(api, item)
                        if error:
                            raise LiveKitAgentDispatchError(error)
                except LiveKitAgentDispatchError:
                    raise
                except Exception as exc:
                    last_error = exc
                    matching_dispatches = []

                if time.monotonic() >= deadline:
                    status = "pending"
                    if matching_dispatches:
                        status = _dispatch_job_status(api, matching_dispatches[-1]) or status
                    message = (
                        f"LiveKit agent '{agent_name}' was not assigned to room "
                        f"'{room}' ({status})"
                    )
                    if last_error is not None:
                        message = f"{message}: {last_error}"
                    raise LiveKitAgentDispatchError(message) from last_error

                await asyncio.sleep(max(poll_interval_seconds, 0.0))
        except LiveKitAgentDispatchError:
            if dispatch_id:
                with suppress(Exception):
                    await client.agent_dispatch.delete_dispatch(dispatch_id, room)
            raise
    finally:
        close = getattr(client, "aclose", None)
        if close is not None:
            await close()
