from __future__ import annotations

from typing import Any

import pytest


class _NoopEnrichmentScheduler:
    """Stand-in that swallows scheduling so tests never make a real enrichment LLM call."""

    def schedule(self, thing_id: str, td: dict[str, Any], *, base_version: int) -> None:
        return None


@pytest.fixture(autouse=True)
def _disable_auto_enrichment(monkeypatch):
    """Globally disable best-effort auto-enrichment scheduling during tests.

    Activating a virtual Thing and minting a record Thing both schedule background
    enrichment via the module-global scheduler. Left live it would fire a real LLM call
    in any test that exercises those paths. Tests that target the scheduler itself
    construct ``VirtualThingEnrichmentScheduler`` instances directly and are unaffected.
    """
    from wotbot.virtual_things import enrichment

    monkeypatch.setattr(enrichment, "_scheduler", _NoopEnrichmentScheduler())
