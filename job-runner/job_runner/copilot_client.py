from __future__ import annotations

from typing import Any

import httpx

from job_runner.settings import Settings


class CopilotClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.copilot_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        token = self._settings.internal_api_key
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def dispatch_prompt(
        self,
        *,
        thread_id: str,
        prompt: str,
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "thread_id": thread_id,
            "prompt": prompt,
            "metadata": metadata,
        }
        async with httpx.AsyncClient(timeout=self._settings.copilot_timeout_seconds) as client:
            response = await client.post(
                f"{self._base_url}/internal/jobs/dispatch",
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()
            body = response.json()
            return body if isinstance(body, dict) else {"ok": True}
