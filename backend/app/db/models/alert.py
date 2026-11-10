from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, generate_uuid


class Alert(Base, TimestampMixin):
    """Environmental threshold alert records."""
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    sensor_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sensors.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_type: Mapped[str] = mapped_column(String(50), nullable=False) # 'temperature', 'humidity', 'leak'
    severity: Mapped[str] = mapped_column(String(20), nullable=False)    # 'warning', 'critical'
    reading_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    message: Mapped[str] = mapped_column(String(255), nullable=False)
    
    status: Mapped[str] = mapped_column(String(30), default="active", index=True) # 'active', 'acknowledged', 'resolved'
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
