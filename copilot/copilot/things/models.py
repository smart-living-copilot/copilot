from dataclasses import dataclass
from datetime import datetime
from typing import Any


ThingDocument = dict[str, Any]


class ThingConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class ThingRecord:
    id: str
    title: str
    description: str
    tags: list[str]
    document: ThingDocument
    document_hash: str


@dataclass(frozen=True)
class ThingRow:
    id: str
    title: str
    description: str
    tags: list[str]
    document: ThingDocument
    document_hash: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
