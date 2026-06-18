"""Best-effort notifications for camera snapshot capture events."""

from __future__ import annotations

import inspect
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import suppress
from threading import Lock

SNAPSHOT_TOPIC = "copilot.camera.snapshot"
SNAPSHOT_EVENT_TYPE = "camera_snapshot_sent"

SnapshotCallback = Callable[[str | None], Awaitable[None] | None]

logger = logging.getLogger(__name__)


class SnapshotNotifierRegistry:
    """In-process callback registry keyed by copilot thread id."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._callbacks_by_thread: dict[str, list[SnapshotCallback]] = defaultdict(list)

    def register(self, thread_id: str, callback: SnapshotCallback) -> Callable[[], None]:
        with self._lock:
            self._callbacks_by_thread[thread_id].append(callback)

        def unregister() -> None:
            with self._lock:
                callbacks = self._callbacks_by_thread.get(thread_id)
                if not callbacks:
                    return
                with suppress(ValueError):
                    callbacks.remove(callback)
                if not callbacks:
                    self._callbacks_by_thread.pop(thread_id, None)

        return unregister

    async def notify_snapshot_sent(self, thread_id: str, captured_at: str | None) -> None:
        with self._lock:
            callbacks = list(self._callbacks_by_thread.get(thread_id, ()))

        for callback in callbacks:
            try:
                result = callback(captured_at)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.debug("Camera snapshot notification callback failed", exc_info=True)


snapshot_notifiers = SnapshotNotifierRegistry()
