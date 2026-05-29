"""Thread metadata models."""

from __future__ import annotations

from typing import TypedDict


class ThreadRecord(TypedDict):
    id: str
    title: str
    createdAt: str
    updatedAt: str
