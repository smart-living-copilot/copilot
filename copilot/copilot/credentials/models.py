import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from copilot.database import Base


class CredentialRow(Base):
    __tablename__ = "thing_credentials"
    __table_args__ = (
        UniqueConstraint("thing_id", "security_name", name="uq_thing_security"),
    )

    id: Mapped[str] = mapped_column(
        Text, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    thing_id: Mapped[str] = mapped_column(Text, nullable=False)
    security_name: Mapped[str] = mapped_column(Text, nullable=False)
    scheme: Mapped[str] = mapped_column(Text, nullable=False)
    credentials: Mapped[dict] = mapped_column(JSON, nullable=False)
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
