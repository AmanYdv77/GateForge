from typing import TYPE_CHECKING

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateforge.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from gateforge.models.api_key import APIKey


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """User account entity owning API keys and subscription tier entitlements."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
        doc="Unique email address for user identification",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Hashed credentials for user dashboard authentication",
    )
    tier: Mapped[str] = mapped_column(
        String(32),
        default="free",
        nullable=False,
        doc="Subscription tier determining default rate limit quotas (free, pro, enterprise)",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        doc="Account active flag for gating access",
    )

    # Relationships
    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
