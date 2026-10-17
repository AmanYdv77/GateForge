import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from gateforge.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from gateforge.models.user import User


class APIKey(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Cryptographic API key entity storing deterministic hash, masked previews, and scope limits."""

    __tablename__ = "api_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        doc="Foreign key pointing to the owning User record",
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Human-readable label for this key (e.g. Production Mobile App)",
    )
    key_prefix: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        doc="First 12 characters of the key for dashboard display",
    )
    key_suffix: Mapped[str] = mapped_column(
        String(8),
        nullable=False,
        doc="Last 4 characters of the key for dashboard display",
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
        doc="Deterministic SHA-256 hash digest used for constant-time lookups",
    )
    scopes: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
        doc="Granted granular permissions (e.g. read:reports, write:orders)",
    )
    custom_rate_limit_rpm: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        doc="Optional custom requests-per-minute quota overriding default tier limits",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        index=True,
        nullable=False,
        doc="Flag indicating whether this key is operational or inactive",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Optional expiration timestamp in UTC",
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp in UTC when this key was revoked, if applicable",
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="api_keys")

    @property
    def masked_display(self) -> str:
        """Return safe formatted masked string for dashboard presentation."""
        return f"{self.key_prefix}••••••••••••{self.key_suffix}"
