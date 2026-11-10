from datetime import datetime
from typing import List, Optional
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Table, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin, generate_uuid


# User to Role many-to-many association table
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", String(36), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")
    permissions: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    users: Mapped[List["User"]] = relationship(
        "User",
        secondary=user_roles,
        back_populates="roles",
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    preferred_lang: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    preferred_theme: Mapped[str] = mapped_column(String(20), default="neon", nullable=False)
    
    # Brute force protection
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    roles: Mapped[List[Role]] = relationship(
        "Role",
        secondary=user_roles,
        back_populates="users",
        lazy="selectin",
    )
    sessions: Mapped[List["UserSession"]] = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    api_tokens: Mapped[List["ApiToken"]] = relationship(
        "ApiToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    @property
    def is_admin(self) -> bool:
        """Check if user has an active Admin role."""
        return any(r.name.lower() == "admin" for r in self.roles)


