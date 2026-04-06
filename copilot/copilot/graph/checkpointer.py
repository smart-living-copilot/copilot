"""Write-through caching wrapper for LangGraph checkpoint savers.

The CopilotKit streaming layer calls ``aget_state()`` on every SSE event
(hundreds per LLM response).  Each call deserialises the full checkpoint
from the underlying store.  This wrapper keeps the most-recent checkpoint
per thread in memory so repeated reads are effectively free.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)

logger = logging.getLogger(__name__)


def _thread_id(config: RunnableConfig) -> str | None:
    return (config.get("configurable") or {}).get("thread_id")


class CachingCheckpointSaver(BaseCheckpointSaver):
    """Thin write-through cache in front of any async checkpoint saver."""

    def __init__(self, underlying: BaseCheckpointSaver) -> None:
        super().__init__(serde=underlying.serde)
        self._underlying = underlying
        # thread_id → most-recent CheckpointTuple
        self._cache: dict[str, CheckpointTuple] = {}

    # -- config specs (delegate) -------------------------------------------

    @property
    def config_specs(self) -> list:
        return self._underlying.config_specs

    # -- reads -------------------------------------------------------------

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        tid = _thread_id(config)
        checkpoint_id = (config.get("configurable") or {}).get("checkpoint_id")

        # Only serve from cache when asking for the *latest* checkpoint
        # (no specific checkpoint_id requested).
        if tid and not checkpoint_id and tid in self._cache:
            return self._cache[tid]

        result = await self._underlying.aget_tuple(config)
        if result and tid and not checkpoint_id:
            self._cache[tid] = result
        return result

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        async for item in self._underlying.alist(config, filter=filter, before=before, limit=limit):
            yield item

    # -- writes ------------------------------------------------------------

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        result = await self._underlying.aput(config, checkpoint, metadata, new_versions)

        # Update cache with the freshly written checkpoint.
        tid = _thread_id(config)
        if tid:
            self._cache[tid] = CheckpointTuple(
                config=result,
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=config,
            )
        return result

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await self._underlying.aput_writes(config, writes, task_id, task_path)
        # Invalidate cache — pending writes change what aget_tuple returns.
        tid = _thread_id(config)
        if tid:
            self._cache.pop(tid, None)

    # -- deletes -----------------------------------------------------------

    async def adelete_thread(self, thread_id: str) -> None:
        await self._underlying.adelete_thread(thread_id)
        self._cache.pop(thread_id, None)

    # -- version -----------------------------------------------------------

    def get_next_version(self, current: Any, channel: None) -> Any:
        return self._underlying.get_next_version(current, channel)
