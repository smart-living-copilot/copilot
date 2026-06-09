from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from copilot.core.orm import Base

ThingDocument = dict[str, Any]


class ThingConflictError(RuntimeError):
    """Raised when a Thing document conflicts with an existing catalog record."""


class Thing(Base):
    __tablename__ = "things"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    document: Mapped[ThingDocument] = mapped_column(JSONB, nullable=False)
    document_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


@dataclass(frozen=True)
class ThingRecord:
    id: str
    title: str
    description: str
    tags: list[str]
    document: ThingDocument
    document_hash: str
