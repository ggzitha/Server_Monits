from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin, generate_uuid


class Sensor(Base, TimestampMixin):
    """Environmental and facility sensors (thermohygrometers, leak ropes, airflow)."""
    __tablename__ = "sensors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    object_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("placed_objects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    data_source_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("data_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Hardware identifier (e.g. MAC, serial, or MQTT subtopic)
    identifier: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sensor_type: Mapped[str] = mapped_column(String(50), default="thermohygrometer", nullable=False)
    
    # Thresholds for alerts
    temp_min_critical: Mapped[Optional[float]] = mapped_column(Float, default=15.0)
    temp_min_warning: Mapped[Optional[float]] = mapped_column(Float, default=18.0)
    temp_max_warning: Mapped[Optional[float]] = mapped_column(Float, default=27.0)
    temp_max_critical: Mapped[Optional[float]] = mapped_column(Float, default=32.0)

    humidity_min_critical: Mapped[Optional[float]] = mapped_column(Float, default=10.0)
    humidity_min_warning: Mapped[Optional[float]] = mapped_column(Float, default=20.0)
    humidity_max_warning: Mapped[Optional[float]] = mapped_column(Float, default=60.0)
    humidity_max_critical: Mapped[Optional[float]] = mapped_column(Float, default=70.0)

    # Live state cache
    current_temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_humidity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    battery_level: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="offline") # online, warning, critical, offline
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Discovery flag: true if auto-detected before operator assignment
    is_discovered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
