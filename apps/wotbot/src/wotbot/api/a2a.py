"""A2A (Agent-to-Agent) JSON-RPC endpoints for WoTBot.

Implements the Google A2A protocol so any A2A-compatible agent can interact
with WoTBot — send messages, receive responses, and retrieve visualizations
as artifacts.

Endpoints:
  GET  /api/a2a/.well-known/agent-card  — Agent card (A2A standard)
  POST /api/a2a/jsonrpc                 — JSON-RPC 2.0 endpoint (methods:
                                          sendMessage, sendMessageStream)
  POST /api/a2a/message                 — Backward-compat simple message API
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from wotbot.api.a2a_protocol import (
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCError,
    SendMessageResult,
    Task,
    TaskState,
    TaskStatus,
    Message,
    Role,
    Artifact,
    Part,
    wotbot_agent_card,
    make_image_part,
    make_message,
)
from wotbot.core.agui_runtime import AguiRuntime

try:
    from ag_ui.core.types import RunAgentInput
except Exception:
    RunAgentInput = None
from wotbot.core.api_dependencies import verify_internal_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/a2a", tags=["a2a"])


# ---------------------------------------------------------------------------
# Backward-compat old request model
# ---------------------------------------------------------------------------


class Attachment(BaseModel):
    type: str = "text"
    data: str = ""
    contentType: str = ""
    displayName: str = ""


class A2AMessage(BaseModel):
    message: str
    threadId: str | None = None
    attachments: list[Attachment] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_runtime(request: Request) -> AguiRuntime:
    try:
        from wotbot.api.main import agui_runtime as _shared_runtime
        return _shared_runtime
    except Exception:
        raise RuntimeError("AG-UI runtime is not available")


def _settings(request: Request) -> Any:
    return getattr(request.app.state, "settings", None)


def _code_executor_url(request: Request) -> str:
    try:
        s = _settings(request)
        if s is not None:
            return s.code_executor_url.rstrip("/")
    except Exception:
        pass
    return "http://localhost:8888"


def _api_key(request: Request) -> str:
    s = _settings(request)
    return s.internal_api_key if s else ""


# ---------------------------------------------------------------------------
# Agent card
# ---------------------------------------------------------------------------


@router.get("/.well-known/agent-card")
async def agent_card_json(request: Request):
    """A2A-standard agent card endpoint."""
    base_url = str(request.base_url).rstrip("/")
    card = wotbot_agent_card(base_url=base_url)
    return JSONResponse(content=card.model_dump())


@router.get("/agent-card")
async def agent_card_legacy(request: Request):
    """Legacy agent card — delegates to the standard endpoint."""
    base_url = str(request.base_url).rstrip("/")
    card = wotbot_agent_card(base_url=base_url)
    return JSONResponse(content=card.model_dump())


# ---------------------------------------------------------------------------
# Artifact proxy — serve code-executor files through WoTBot
# ---------------------------------------------------------------------------


@router.get("/artifacts/{filename:path}")
async def proxy_artifact(filename: str, request: Request):
    """Proxy artifact files from the code executor.

    This allows A2A callers to fetch artifact content via a WoTBot URL
    (``/api/a2a/artifacts/{filename}``) without needing direct access to the
    code executor service.
    """
    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    executor_url = _code_executor_url(request)
    api_key = _api_key(request)
    result = await _fetch_artifact(executor_url, filename, api_key)
    if result is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return Response(
        content=result["body"],
        media_type=result["content_type"],
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Artifact fetching from the code executor
# ---------------------------------------------------------------------------


async def _fetch_artifact(
    executor_url: str, filename: str, api_key: str
) -> dict[str, Any] | None:
    safe = "/" not in filename and "\\" not in filename and ".." not in filename
    if not safe or not filename:
        return None
    url = f"{executor_url}/artifacts/{filename}"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Could not fetch artifact %s: %s", filename, exc)
        return None
    body = resp.content
    return {"filename": filename, "body": body, "content_type": resp.headers.get("content-type", "application/octet-stream")}


async def _collect_artifact_parts(events: list[Any], executor_url: str, api_key: str, base_url: str = "") -> list[Part]:
    """Scan events for artifact filenames, fetch from code executor, return as A2A Parts."""
    filenames: set[str] = set()
    for event in events:
        if hasattr(event, "model_dump"):
            event_dict = event.model_dump()
        elif hasattr(event, "dict"):
            event_dict = event.dict()
        elif isinstance(event, dict):
            event_dict = event
        else:
            continue
        if event_dict.get("type") == "RAW":
            raw = event_dict.get("event") or {}
            if not isinstance(raw, dict):
                continue
            if raw.get("event") in ("on_tool_end", "on_chain_end"):
                output = raw.get("data", {}).get("output") or {}
                if not isinstance(output, dict):
                    continue
                content = output.get("content")
                if isinstance(content, str) and "artifacts" in content:
                    try:
                        parsed = json.loads(content)
                        if isinstance(parsed, dict):
                            for art in parsed.get("artifacts", []):
                                fn = art.get("filename") if isinstance(art, dict) else None
                                if isinstance(fn, str) and fn:
                                    filenames.add(fn)
                    except Exception:
                        pass

    if not filenames:
        return []

    results = await asyncio.gather(
        *[_fetch_artifact(executor_url, fn, api_key) for fn in filenames],
        return_exceptions=True,
    )
    parts: list[Part] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        fn = r["filename"]
        body = r["body"]
        ct = r["content_type"]
        art_url = f"{base_url}/api/a2a/artifacts/{fn}" if base_url else ""
        if fn.endswith(".png"):
            parts.append(make_image_part(base64.b64encode(body).decode(), "image/png", url=art_url))
        elif fn.endswith((".html", ".json")):
            parts.append(Part(text="", mime_type="text/html", url=art_url, inline_data=body.decode("utf-8", errors="replace")))
        else:
            parts.append(make_image_part(base64.b64encode(body).decode(), ct, url=art_url))
    return parts


# ---------------------------------------------------------------------------
# Run the agent and produce a Task result
# ---------------------------------------------------------------------------


async def _run_agent(
    runtime: AguiRuntime,
    message_text: str,
    thread_id: str,
    run_id: str,
    executor_url: str,
    api_key: str,
    base_url: str = "",
    attachments: list[Attachment] | None = None,
) -> Task:
    """Run the WoTBot agent and return a completed Task with response text + artifacts."""
    content_blocks: list[dict[str, Any]] = [{"type": "text", "text": message_text}]

    if attachments:
        for att in attachments:
            if att.type == "image" and att.data:
                content_blocks.append({"type": "image_url", "image_url": {"url": att.data}})
            elif att.type == "text" and att.data:
                content_blocks.append({"type": "text", "text": att.data})
            elif att.type == "file" and att.data:
                try:
                    decoded = base64.b64decode(att.data).decode("utf-8", errors="replace")
                    label = att.displayName or "attached file"
                    content_blocks.append({"type": "text", "text": f"[Attachment: {label} ({att.contentType})]\n{decoded[:10000]}"})
                except Exception:
                    content_blocks.append({"type": "text", "text": f"[Attachment: {att.displayName or 'file'} ({att.contentType}) — binary data, {len(att.data)} base64 chars]"})

    input_dict = {
        "threadId": thread_id,
        "thread_id": thread_id,
        "runId": run_id,
        "run_id": run_id,
        "state": {},
        "messages": [{"id": f"msg-{uuid4().hex}", "role": "user", "content": content_blocks}],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }

    input_data = input_dict
    if RunAgentInput is not None:
        try:
            try:
                input_data = RunAgentInput.model_validate(input_dict)
            except Exception:
                input_data = RunAgentInput(**input_dict)
        except Exception:
            input_data = input_dict

    def _wrap_compat(value):
        if isinstance(value, dict):
            return _RunInputCompat({k: _wrap_compat(v) for k, v in value.items()})
        if isinstance(value, list):
            return [_wrap_compat(v) for v in value]
        return value

    class _RunInputCompat(dict):
        def __init__(self, value):
            if isinstance(value, dict):
                super().__init__(value)
            elif hasattr(value, "dict") and callable(value.dict):
                super().__init__({k: _wrap_compat(v) for k, v in value.dict().items()})
            else:
                super().__init__(value)
        def __getattr__(self, name):
            if name in self:
                return self[name]
            raise AttributeError(name)
        def copy(self, update=None, **kwargs):
            result = dict(self)
            if update is not None:
                result.update(update)
            result.update(kwargs)
            return _RunInputCompat({k: _wrap_compat(v) for k, v in result.items()})
        def model_copy(self, update=None, **kwargs):
            return self.copy(update=update or {}, **kwargs)
        def dict(self):
            def _unwrap(value):
                if isinstance(value, _RunInputCompat):
                    return {k: _unwrap(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [_unwrap(v) for v in value]
                return value
            return {k: _unwrap(v) for k, v in self.items()}

    if not isinstance(input_data, _RunInputCompat):
        input_data = _wrap_compat(input_data)

    events: list[Any] = []
    try:
        proxy = runtime.create_agent_proxy()
        async for event in proxy.run(input_data):
            events.append(event)
    except asyncio.CancelledError:
        raise HTTPException(status_code=499, detail="Request cancelled")
    except Exception as exc:
        logger.exception("A2A run failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    # Extract response text from events
    response_text = "(no response)"
    for event in events:
        if hasattr(event, "model_dump"):
            ed = event.model_dump()
        elif hasattr(event, "dict"):
            ed = event.dict()
        elif isinstance(event, dict):
            ed = event
        else:
            continue
        if ed.get("type") == "RAW":
            raw = ed.get("event") or {}
            if raw.get("event") == "on_chat_model_end":
                output = raw.get("data", {}).get("output") or {}
                content = output.get("content") or ""
                if isinstance(content, str) and len(content) > 10:
                    if not (content.strip().startswith("{") and content.strip().endswith("}")):
                        response_text = content

    # Build the A2A Task result
    artifact_parts = await _collect_artifact_parts(events, executor_url, api_key, base_url)

    task = Task(
        id=run_id,
        context_id=thread_id,
        status=TaskStatus(
            state=TaskState.COMPLETED,
            message=make_message(response_text, role=Role.ASSISTANT),
        ),
    )

    if artifact_parts:
        task.artifacts.append(
            Artifact(
                artifact_id=str(uuid4()),
                name="Agent Output",
                description="Visualizations and files generated by the agent",
                parts=artifact_parts,
            )
        )

    return task


# ---------------------------------------------------------------------------
# JSON-RPC endpoint
# ---------------------------------------------------------------------------


@router.post("/jsonrpc")
async def jsonrpc_endpoint(body: JSONRPCRequest, request: Request):
    """JSON-RPC 2.0 endpoint for the A2A protocol.

    Supported methods:
      - ``sendMessage`` — send a message, get a Task back
      - ``sendMessageStream`` — send a message, get a streaming TaskStatusUpdateEvent
    """
    runtime = _agent_runtime(request)
    if runtime is None:
        return JSONResponse(
            content=JSONRPCResponse(id=body.id, error=JSONRPCError(code=-32000, message="AG-UI runtime not available")).model_dump(),
            status_code=503,
        )

    if body.method == "sendMessage":
        return await _handle_send_message(body, runtime, request)
    elif body.method == "sendMessageStream":
        return await _handle_send_message_stream(body, runtime, request)
    else:
        return JSONResponse(
            content=JSONRPCResponse(id=body.id, error=JSONRPCError(code=-32601, message=f"Method not found: {body.method}")).model_dump(),
            status_code=400,
        )


async def _handle_send_message(body: JSONRPCRequest, runtime: AguiRuntime, request: Request) -> JSONResponse:
    """Handle a sendMessage JSON-RPC call."""
    executor_url = _code_executor_url(request)
    api_key = _api_key(request)
    params = body.params or {}
    message_text = ""
    context_id = ""
    attachments: list[Attachment] = []

    # Extract from A2A protocol format
    if "message" in params:
        msg_data = params["message"]
        if isinstance(msg_data, dict):
            parts = msg_data.get("parts", [])
            if parts and isinstance(parts, list):
                for p in parts:
                    if isinstance(p, dict):
                        text = p.get("text", "")
                        if text:
                            message_text += text + "\n"
            context_id = msg_data.get("context_id", "")
            # Check for attachment data
            for p in parts:
                if isinstance(p, dict) and p.get("inline_data"):
                    attachments.append(Attachment(type="image", data=p["inline_data"], contentType=p.get("mime_type", "")))
        elif isinstance(msg_data, str):
            message_text = msg_data

    message_text = message_text.strip()
    if not message_text:
        return JSONResponse(
            content=JSONRPCResponse(id=body.id, error=JSONRPCError(code=-32602, message="No message text provided")).model_dump(),
            status_code=400,
        )

    thread_id = context_id or f"a2a-{uuid4().hex}"
    run_id = uuid4().hex
    base_url = str(request.base_url).rstrip("/")

    try:
        task = await _run_agent(runtime, message_text, thread_id, run_id, executor_url, api_key, base_url, attachments)
    except HTTPException as exc:
        task = Task(
            id=run_id,
            context_id=thread_id,
            status=TaskStatus(state=TaskState.FAILED, message=make_message(str(exc.detail), role=Role.ASSISTANT)),
        )

    result = SendMessageResult(task=task)
    return JSONResponse(
        content=JSONRPCResponse(id=body.id, result=result.model_dump()).model_dump(),
    )


async def _handle_send_message_stream(body: JSONRPCRequest, runtime: AguiRuntime, request: Request) -> JSONResponse:
    """Handle a sendMessageStream call — returns final result (streaming via SSE not yet implemented)."""
    return await _handle_send_message(body, runtime, request)


# ---------------------------------------------------------------------------
# Backward-compatible simple message endpoint
# ---------------------------------------------------------------------------


@router.post("/message")
async def post_message(
    body: A2AMessage,
    request: Request,
    _ok: Any = Depends(verify_internal_api_key),
):
    """Legacy simple message endpoint.  Returns the same format as before."""
    runtime = _agent_runtime(request)
    if runtime is None:
        raise HTTPException(status_code=503, detail="AG-UI runtime not available")

    executor_url = _code_executor_url(request)
    api_key = _api_key(request)
    base_url = str(request.base_url).rstrip("/")
    thread_id = body.threadId or f"embed-ephemeral-{uuid4().hex}"
    run_id = uuid4().hex

    try:
        task = await _run_agent(runtime, body.message, thread_id, run_id, executor_url, api_key, base_url, body.attachments or None)
    except HTTPException as exc:
        raise exc

    # Collect events for backward compat
    events = []
    if task.status.message:
        for p in task.status.message.parts:
            if p.text:
                events.append({"type": "text", "content": p.text})
    for art in task.artifacts:
        for p in art.parts:
            events.append({
                "type": "A2A_ARTIFACTS",
                "artifacts": [{
                    "filename": art.artifact_id,
                    "kind": "image" if "image" in p.mime_type else "plotly",
                    "media_type": p.mime_type,
                    "base64": p.inline_data if p.inline_data else "",
                }],
            })

    return {
        "ok": task.status.state == TaskState.COMPLETED,
        "thread_id": thread_id,
        "run_id": run_id,
        "events": events,
        "task": task.model_dump(),
    }
