from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from wotbot.core.orm import Base


class VirtualThing(Base):
    """Abstract virtual Thing definition owned by wotbot."""

    __tablename__ = "virtual_things"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    owner_thread_id: Mapped[str | None] = mapped_column(Text)
    abstract_td: Mapped[Any] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="active")
    shared_state: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    shared_state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
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


class VirtualThingBinding(Base):
    """Per-affordance dispatch binding for a virtual Thing."""

    __tablename__ = "virtual_thing_bindings"
    __table_args__ = (
        UniqueConstraint(
            "thing_id",
            "affordance_type",
            "affordance_name",
            name="uq_virtual_thing_binding_affordance",
        ),
        Index("idx_virtual_thing_bindings_thing", "thing_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    thing_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("virtual_things.id", ondelete="CASCADE"),
        nullable=False,
    )
    affordance_type: Mapped[str] = mapped_column(Text, nullable=False)
    affordance_name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    handler_code: Mapped[str | None] = mapped_column(Text)
    config: Mapped[Any] = mapped_column(JSONB, nullable=False, default=dict)
    capabilities: Mapped[Any] = mapped_column(JSONB, nullable=False, default=list)
    trigger: Mapped[Any | None] = mapped_column(JSONB)
    state: Mapped[Any | None] = mapped_column(JSONB)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    cache_ttl_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
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
