from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, generate_uuid


class AlertRule(Base, TimestampMixin):
    """Configurable threshold alerting rules (Full CRUD) evaluated against live sensors, racks & security."""
    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # all_sensors | sensor | rack_power | security
    target_scope: Mapped[str] = mapped_column(String(32), default="all_sensors", nullable=False, index=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # temperature | humidity | power_kw | rack_power_pct
    metric_type: Mapped[str] = mapped_column(String(40), default="temperature", nullable=False)
    # gt | gte | lt | lte
    operator: Mapped[str] = mapped_column(String(12), default="gt", nullable=False)
    warning_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    critical_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=30.0)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    notify_webhook_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


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
