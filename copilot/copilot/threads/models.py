"""Thread metadata models."""

from __future__ import annotations

from typing import TypedDict

DEFAULT_THREAD_TITLE = "New Chat"


class ThreadRecord(TypedDict):
    id: str
    title: str
    createdAt: str
    updatedAt: str
