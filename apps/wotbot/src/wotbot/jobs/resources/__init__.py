"""Job external resource definitions.

This package tracks resources a job depends on (schedules, event subscriptions,
and structured-record virtual Thing registrations), plus helpers that reconcile
those resources when jobs are activated, updated, or removed.
"""

from __future__ import annotations

from wotbot.jobs.resources.constants import (
    RESOURCE_EVENT_SUBSCRIPTION,
    RESOURCE_SCHEDULE,
    RESOURCE_VIRTUAL_RECORD_THING,
)
from wotbot.jobs.resources.event_subscriptions import EventSubscriptionReconciler
from wotbot.jobs.resources.manager import JobResourceManager, PreparedJobResources

__all__ = [
    "RESOURCE_EVENT_SUBSCRIPTION",
    "RESOURCE_SCHEDULE",
    "RESOURCE_VIRTUAL_RECORD_THING",
    "EventSubscriptionReconciler",
    "JobResourceManager",
    "PreparedJobResources",
]
