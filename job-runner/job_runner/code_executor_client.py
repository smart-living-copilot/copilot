from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from job_runner.settings import Settings


logger = logging.getLogger(__name__)


class CodeExecutorClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.code_executor_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        token = self._settings.internal_api_key
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def execute(self, *, session_id: str, code: str) -> dict[str, Any]:
        attempts = max(1, self._settings.code_executor_retry_attempts)
        base_backoff = max(0.0, self._settings.code_executor_retry_backoff_seconds)

        last_error: Exception | None = None
        async with httpx.AsyncClient(timeout=self._settings.code_executor_timeout_seconds) as client:
            for attempt in range(1, attempts + 1):
                try:
                    response = await client.post(
                        f"{self._base_url}/execute",
                        json={"session_id": session_id, "code": code},
                        headers=self._headers(),
                    )
                    response.raise_for_status()
                    body = response.json()
                    return body if isinstance(body, dict) else {}
                except (httpx.TransportError, httpx.TimeoutException) as exc:
                    last_error = exc
                    if attempt >= attempts:
                        break
                    sleep_seconds = base_backoff * (2 ** (attempt - 1))
                    logger.warning(
                        "Code executor request failed (attempt %s/%s): %s; retrying in %.2fs",
                        attempt,
                        attempts,
                        exc,
                        sleep_seconds,
                    )
                    if sleep_seconds > 0:
                        await asyncio.sleep(sleep_seconds)
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    status = exc.response.status_code
                    retriable = status in {429, 502, 503, 504}
                    if not retriable or attempt >= attempts:
                        raise
                    sleep_seconds = base_backoff * (2 ** (attempt - 1))
                    logger.warning(
                        "Code executor returned %s (attempt %s/%s); retrying in %.2fs",
                        status,
                        attempt,
                        attempts,
                        sleep_seconds,
                    )
                    if sleep_seconds > 0:
                        await asyncio.sleep(sleep_seconds)

        if last_error is not None:
            raise last_error
        raise RuntimeError("Code executor request failed without an explicit exception")
