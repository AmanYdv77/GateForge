import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base declarative class for all GateForge persistence models."""

    pass


class UUIDPrimaryKeyMixin:
    """Mixin providing an immutable UUID primary key across PostgreSQL and SQLite engines."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        sort_order=-10,
        doc="Unique identifier (v4 UUID)",
    )


class TimestampMixin:
    """Mixin providing timezone-aware created_at and updated_at audit timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        sort_order=100,
        doc="Timestamp in UTC when the record was inserted",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        sort_order=101,
        doc="Timestamp in UTC when the record was last modified",
    )
