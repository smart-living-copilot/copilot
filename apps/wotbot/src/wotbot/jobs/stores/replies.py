from __future__ import annotations

from typing import Any

from wotbot.jobs.db import JobRunRecord
from wotbot.jobs.schemas import JobRun
from wotbot.jobs.stores.base import _to_job_run


def _normalize_client_reply_id(client_reply_id: str | None) -> str | None:
    normalized = (client_reply_id or "").strip()
    return normalized or None


def _reply_payload_has_client_reply_id(payload: Any, client_reply_id: str) -> bool:
    if not isinstance(payload, dict):
        return False
    replies = payload.get("replies")
    if not isinstance(replies, list):
        return False
    for reply in replies:
        if not isinstance(reply, dict):
            continue
        if reply.get("client_reply_id") == client_reply_id:
            return True
    return False


def _duplicate_reply_run(row: JobRunRecord) -> JobRun:
    run = _to_job_run(row)
    trigger_payload = run.trigger_payload if isinstance(run.trigger_payload, dict) else {}
    run.trigger_payload = {
        **trigger_payload,
        "_duplicate_reply": True,
    }
    return run
