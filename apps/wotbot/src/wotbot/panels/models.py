from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from wotbot.core.orm import Base

PanelCapabilities = list[dict[str, Any]]


class Panel(Base):
    """A pinned generative WoT mini-interface.

    Stores the agent's raw body markup (re-wrapped at render time so the latest
    bridge/CSP applies) plus the capability allowlist the UI enforces. Decoupled
    from chats: ``source_thread_id`` is soft provenance only, never a foreign
    key, so deleting a conversation never removes a pinned panel.
    """

    __tablename__ = "panels"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    html: Mapped[str] = mapped_column(Text, nullable=False)
    capabilities: Mapped[PanelCapabilities] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    source_thread_id: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class PanelVersion(Base):
    """Immutable saved state for a panel."""

    __tablename__ = "panel_versions"
    __table_args__ = (
        UniqueConstraint("panel_id", "version", name="uq_panel_versions_panel_version"),
        Index("ix_panel_versions_panel_id_created_at", "panel_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    panel_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("panels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column("version", Integer, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    html: Mapped[str] = mapped_column(Text, nullable=False)
    capabilities: Mapped[PanelCapabilities] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
