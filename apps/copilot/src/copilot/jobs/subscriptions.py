from __future__ import annotations

from typing import Any


def subscription_id_from_response(response: dict[str, Any] | str) -> str:
    if isinstance(response, str):
        return response

    subscription = response.get("subscription", {})
    if not isinstance(subscription, dict):
        subscription = {}

    subscription_id = (
        subscription.get("subscriptionId")
        or subscription.get("subscription_id")
        or response.get("subscriptionId")
        or response.get("subscription_id")
    )
    if not subscription_id:
        raise ValueError("Runtime did not return a subscription id")
    return str(subscription_id)
