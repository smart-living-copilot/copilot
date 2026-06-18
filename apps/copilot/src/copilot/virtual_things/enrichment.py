"""Best-effort, supersedeable semantic enrichment of virtual Things.

Enrichment is an LLM call, so it runs *after* a virtual Thing is activated rather than
blocking (or failing) activation. The race this guards against:

    create → add property → activate (v1)  →  add property → activate (v2)

The first activation's enrichment may still be running against the v1 TD when v2 lands.
Two mechanisms keep that safe:

* **Supersession** — scheduling enrichment for a Thing cancels the prior in-flight task
  for the same Thing, so the stale LLM call is abandoned (and its cost saved).
* **Version compare-and-set** — the result is written back only if the Thing is still at
  the version that was enriched (see ``VirtualThingStore.apply_enrichment``). Even if a
  cancelled task slips through, a bumped version discards its stale TD.

Everything here is best-effort: any failure (no network, no API key, no valid proposal)
is logged and dropped, so the booth demo still works offline.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

EnrichFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]
ApplyFn = Callable[[str, dict[str, Any], int], Awaitable[bool]]

# Enrichment is scheduled inside the activate tool, so its LLM call inherits the agent
# run's streaming context and would otherwise stream the enriched TD back to the chat UI.
# These flags tell the AG-UI (plain keys) and CopilotKit (copilotkit:-prefixed keys)
# stream adapters to drop this run's tokens.
_SILENT_RUN_CONFIG: dict[str, Any] = {
    "tags": ["virtual-thing-enrichment"],
    "metadata": {
        "emit-messages": False,
        "emit-tool-calls": False,
        "copilotkit:emit-messages": False,
        "copilotkit:emit-tool-calls": False,
    },
}


class VirtualThingEnrichmentScheduler:
    """Schedules per-Thing enrichment tasks, cancelling any superseded one."""

    def __init__(self, *, enrich: EnrichFn | None = None, apply: ApplyFn | None = None) -> None:
        self._enrich = enrich or _default_enrich
        self._apply = apply or _default_apply
        self._tasks: dict[str, asyncio.Task[None]] = {}

    def schedule(
        self, thing_id: str, td: dict[str, Any], *, base_version: int
    ) -> asyncio.Task[None] | None:
        """Cancel any in-flight enrichment for ``thing_id`` and start a fresh one.

        Returns the created task (handy for tests/awaiting), or ``None`` when no event
        loop is running so enrichment cannot be scheduled.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("No running event loop; skipping enrichment for %s", thing_id)
            return None

        prior = self._tasks.get(thing_id)
        if prior is not None and not prior.done():
            prior.cancel()

        task = loop.create_task(self._run(thing_id, td, base_version))
        self._tasks[thing_id] = task
        task.add_done_callback(lambda finished, tid=thing_id: self._forget(tid, finished))
        return task

    def _forget(self, thing_id: str, task: asyncio.Task[None]) -> None:
        if self._tasks.get(thing_id) is task:
            self._tasks.pop(thing_id, None)

    async def _run(self, thing_id: str, td: dict[str, Any], base_version: int) -> None:
        try:
            enriched = await self._enrich(td)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # best-effort: never let enrichment break the flow
            logger.info("Enrichment skipped for %s: %s", thing_id, exc)
            return
        if enriched is None:
            return
        applied = await self._apply(thing_id, enriched, base_version)
        if applied:
            logger.info("Applied semantic enrichment to %s (from v%s)", thing_id, base_version)
        else:
            logger.debug("Enrichment for %s superseded (no longer v%s)", thing_id, base_version)


async def _default_enrich(td: dict[str, Any]) -> dict[str, Any] | None:
    from copilot.catalog.enrichment.config import load_enrichment_config
    from copilot.catalog.enrichment.service import EnrichmentError, enrich_thing_document
    from copilot.core.config import Settings
    from copilot.core.llm import make_llm

    settings = Settings()
    config = load_enrichment_config(settings.thing_enrichment_config_path)
    llm = make_llm(settings)
    try:
        result = await enrich_thing_document(
            td,
            config=config,
            llm=llm,
            max_repair_attempts=settings.thing_enrichment_max_repair_attempts,
            runnable_config=_SILENT_RUN_CONFIG,
        )
    except EnrichmentError as exc:
        logger.info("Enrichment produced no valid proposal: %s", exc)
        return None
    return result.enriched


async def _default_apply(thing_id: str, enriched: dict[str, Any], base_version: int) -> bool:
    return await asyncio.to_thread(
        _default_store().apply_enrichment, thing_id, enriched, base_version=base_version
    )


def _default_store() -> Any:
    from copilot.virtual_things.store import VirtualThingStore

    return VirtualThingStore()


_scheduler: VirtualThingEnrichmentScheduler | None = None


def get_enrichment_scheduler() -> VirtualThingEnrichmentScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = VirtualThingEnrichmentScheduler()
    return _scheduler
