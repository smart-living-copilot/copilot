"""Thread metadata and title management.

The threads package owns persistent thread records for chat/job context and
stores metadata used to surface readable thread lists and suggested titles in UI
and job workflows.
"""

from copilot.threads.models import ThreadKind
from copilot.threads.store import (
    create_thread,
    delete_thread,
    get_thread,
    list_threads,
    sync_thread_after_run,
    touch_thread,
    update_thread_title,
)
from copilot.threads.titles import suggest_thread_title

__all__ = [
    "ThreadKind",
    "create_thread",
    "delete_thread",
    "get_thread",
    "list_threads",
    "suggest_thread_title",
    "sync_thread_after_run",
    "touch_thread",
    "update_thread_title",
]
