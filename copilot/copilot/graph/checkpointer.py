"""Caching wrapper for LangGraph checkpoint savers.

The CopilotKit streaming layer calls ``aget_state()`` on every SSE event
(hundreds per LLM response).  Each call deserialises the full checkpoint
from the underlying store.  This wrapper keeps the most-recent checkpoint
per thread in memory so repeated reads are effectively free.

Writes are deferred to a pending queue and only flushed to the underlying
store when ``flush()`` is called (typically once per completed request).
This avoids blocking graph execution with SQLite I/O on every node.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
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


type PendingPut = tuple[RunnableConfig, Checkpoint, CheckpointMetadata, ChannelVersions]
type PendingWrite = tuple[RunnableConfig, Sequence[tuple[str, Any]], str, str]


@dataclass(slots=True)
class _PendingThreadOperations:
    puts: list[PendingPut] = field(default_factory=list)
    writes: list[PendingWrite] = field(default_factory=list)


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
        # Thread-local pending writes to flush.
        self._pending_by_thread: dict[str | None, _PendingThreadOperations] = {}
        # Deleted threads are tombstoned so in-flight runs cannot resurrect them.
        self._deleted_threads: set[str] = set()
        self._state_lock = asyncio.Lock()

    # -- config specs (delegate) -------------------------------------------

    @property
    def config_specs(self) -> list:
        return self._underlying.config_specs

    # -- reads -------------------------------------------------------------

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        tid = _thread_id(config)
        checkpoint_id = (config.get("configurable") or {}).get("checkpoint_id")

        async with self._state_lock:
            if tid and tid in self._deleted_threads:
                return None

            # Only serve from cache when asking for the *latest* checkpoint
            # (no specific checkpoint_id requested).
            if tid and not checkpoint_id and tid in self._cache:
                return self._cache[tid]

        result = await self._underlying.aget_tuple(config)
        if result and tid and not checkpoint_id:
            async with self._state_lock:
                if tid not in self._deleted_threads:
                    self._cache[tid] = result
                else:
                    return None
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

        async with self._state_lock:
            if tid and tid in self._deleted_threads:
                logger.info("Dropping checkpoint write for deleted thread %s", tid)
                return result

            # Update cache so subsequent reads see the latest state.
            if tid:
                self._cache[tid] = CheckpointTuple(
                    config=result,
                    checkpoint=checkpoint,
                    metadata=metadata,
                    parent_config=config,
                )

            pending = self._pending_by_thread.setdefault(tid, _PendingThreadOperations())
            pending.puts.append((config, checkpoint, metadata, new_versions))
        return result

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        tid = _thread_id(config)
        async with self._state_lock:
            if tid and tid in self._deleted_threads:
                logger.info("Dropping pending tool writes for deleted thread %s", tid)
                return

            pending = self._pending_by_thread.setdefault(tid, _PendingThreadOperations())
            pending.writes.append((config, writes, task_id, task_path))

    # -- flush -------------------------------------------------------------

    async def flush(self, thread_id: str | None = None) -> None:
        """Write pending operations to the underlying store.

        When ``thread_id`` is provided, only that thread's deferred writes are
        flushed. Otherwise all pending threads are flushed.
        """
        async with self._state_lock:
            if thread_id is None:
                pending_batches = list(self._pending_by_thread.values())
                self._pending_by_thread = {}
            else:
                pending = self._pending_by_thread.pop(thread_id, None)
                pending_batches = [pending] if pending else []

        for pending in pending_batches:
            if pending is None:
                continue

            for config, writes, task_id, task_path in pending.writes:
                await self._underlying.aput_writes(config, writes, task_id, task_path)

            for config, checkpoint, metadata, new_versions in pending.puts:
                await self._underlying.aput(config, checkpoint, metadata, new_versions)

    async def pending_thread_ids(self) -> list[str | None]:
        async with self._state_lock:
            return list(self._pending_by_thread.keys())

    # -- deletes -----------------------------------------------------------

    async def adelete_thread(self, thread_id: str) -> None:
        async with self._state_lock:
            self._deleted_threads.add(thread_id)
            cached = self._cache.pop(thread_id, None)
            pending = self._pending_by_thread.pop(thread_id, None)

        try:
            await self._underlying.adelete_thread(thread_id)
        except Exception:
            async with self._state_lock:
                self._deleted_threads.discard(thread_id)
                if cached is not None:
                    self._cache[thread_id] = cached
                if pending is not None and (pending.puts or pending.writes):
                    self._pending_by_thread[thread_id] = pending
            raise

    async def is_deleted_thread(self, thread_id: str) -> bool:
        async with self._state_lock:
            return thread_id in self._deleted_threads

    # -- version -----------------------------------------------------------

    def get_next_version(self, current: Any, channel: None) -> Any:
        return self._underlying.get_next_version(current, channel)
