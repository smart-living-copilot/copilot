"""Write-through caching wrapper for LangGraph checkpoint savers.

The CopilotKit streaming layer calls ``aget_state()`` on every SSE event
(hundreds per LLM response).  Each call deserialises the full checkpoint
from the underlying store.  This wrapper keeps the most-recent checkpoint
per thread in memory so repeated reads are effectively free.

Writes are deferred to a pending queue and only flushed to the underlying
store when ``flush()`` is called (typically once per completed request).
This avoids blocking graph execution with SQLite I/O on every node.
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
    """Thin write-behind cache in front of any async checkpoint saver.

    Reads are served from an in-memory cache.  Writes are buffered and
    flushed to the underlying saver explicitly via ``flush()``.
    """

    def __init__(self, underlying: BaseCheckpointSaver) -> None:
        super().__init__(serde=underlying.serde)
        self._underlying = underlying
        # thread_id → most-recent CheckpointTuple
        self._cache: dict[str, CheckpointTuple] = {}
        # Pending writes to flush
        self._pending_puts: list[tuple[RunnableConfig, Checkpoint, CheckpointMetadata, ChannelVersions]] = []
        self._pending_writes: list[tuple[RunnableConfig, Sequence[tuple[str, Any]], str, str]] = []

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

    # -- writes (deferred) -------------------------------------------------

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        tid = _thread_id(config)
        checkpoint_ns = (config.get("configurable") or {}).get("checkpoint_ns", "")

        result: RunnableConfig = {
            "configurable": {
                "thread_id": tid,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint["id"],
            }
        }

        # Update cache so subsequent reads see the latest state.
        if tid:
            self._cache[tid] = CheckpointTuple(
                config=result,
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=config,
            )

        self._pending_puts.append((config, checkpoint, metadata, new_versions))
        return result

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        self._pending_writes.append((config, writes, task_id, task_path))

    # -- flush -------------------------------------------------------------

    async def flush(self) -> None:
        """Write all pending operations to the underlying store."""
        if not self._pending_writes and not self._pending_puts:
            return

        for config, writes, task_id, task_path in self._pending_writes:
            await self._underlying.aput_writes(config, writes, task_id, task_path)
        self._pending_writes.clear()

        for config, checkpoint, metadata, new_versions in self._pending_puts:
            await self._underlying.aput(config, checkpoint, metadata, new_versions)
        self._pending_puts.clear()

    # -- deletes -----------------------------------------------------------

    async def adelete_thread(self, thread_id: str) -> None:
        await self._underlying.adelete_thread(thread_id)
        self._cache.pop(thread_id, None)

    # -- version -----------------------------------------------------------

    def get_next_version(self, current: Any, channel: None) -> Any:
        return self._underlying.get_next_version(current, channel)
