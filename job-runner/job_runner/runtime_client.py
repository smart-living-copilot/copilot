from __future__ import annotations

from typing import Any

import httpx

from job_runner.settings import Settings


class WotRuntimeClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.wot_runtime_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        token = self._settings.wot_runtime_api_token
        return {"Authorization": f"Bearer {token}"} if token else {}

    async def subscribe_event(
        self,
        *,
        thing_id: str,
        event_name: str,
        subscription_input: Any = None,
    ) -> str:
        payload = {
            "thing_id": thing_id,
            "event_name": event_name,
            "subscription_input": subscription_input,
        }
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self._base_url}/runtime/subscribe-event",
                json=payload,
                headers=self._headers(),
            )
            response.raise_for_status()
            body = response.json()

        subscription = body.get("subscription", {}) if isinstance(body, dict) else {}
        subscription_id = (
            subscription.get("subscriptionId")
            or subscription.get("subscription_id")
            or body.get("subscription_id")
        )
        if not subscription_id:
            raise ValueError("Runtime did not return a subscription id")
        return str(subscription_id)

    async def remove_subscription(self, subscription_id: str) -> None:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{self._base_url}/runtime/remove-subscription",
                json={"subscription_id": subscription_id},
                headers=self._headers(),
            )
            response.raise_for_status()
