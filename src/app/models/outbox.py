import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

JSONType = JSONB().with_variant(JSON(), "sqlite")


class OutboxStatus(str, enum.Enum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


class OutboxEvent(Base):
    """Transactional outbox row"""

    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONType, nullable=False)

    status: Mapped[OutboxStatus] = mapped_column(
        Enum(OutboxStatus, name="outbox_status"),
        nullable=False,
        default=OutboxStatus.PENDING,
        index=True,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"OutboxEvent(id={self.id}, event_type={self.event_type}, status={self.status})"
