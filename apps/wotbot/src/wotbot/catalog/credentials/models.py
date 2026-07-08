from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from wotbot.core.orm import Base


class ThingCredential(Base):
    __tablename__ = "thing_credentials"
    __table_args__ = (UniqueConstraint("thing_id", "security_name", name="uq_thing_security"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    thing_id: Mapped[str] = mapped_column(Text, nullable=False)
    security_name: Mapped[str] = mapped_column(Text, nullable=False)
    scheme: Mapped[str] = mapped_column(Text, nullable=False)
    credentials: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
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
class CredentialRecord:
    id: str
    thing_id: str
    security_name: str
    scheme: str
    credentials: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None
