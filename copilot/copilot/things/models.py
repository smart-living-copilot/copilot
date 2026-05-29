from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from copilot.database import Base


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


class ThingRow(Base):
    __tablename__ = "things"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    document: Mapped[ThingDocument] = mapped_column(JSON, nullable=False)
    document_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
