"""Thread metadata models."""

from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Index, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DEFAULT_THREAD_TITLE = "New Chat"


class Base(DeclarativeBase):
    pass


class Thread(Base):
    __tablename__ = "threads"
    __table_args__ = (
        Index("idx_threads_updated_at", "updated_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False, default=DEFAULT_THREAD_TITLE)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class ThreadRecord(TypedDict):
    id: str
    title: str
    createdAt: str
    updatedAt: str


class CreateThreadRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    title: str | None = None
    created_at: str | None = Field(default=None, alias="createdAt")
    updated_at: str | None = Field(default=None, alias="updatedAt")


class UpdateThreadTitleRequest(BaseModel):
    title: str
    force: bool = False

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Title is required")
        return title
