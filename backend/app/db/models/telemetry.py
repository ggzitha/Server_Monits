from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import BigInteger, Integer, DateTime, Float, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class TelemetryReading(Base):
    __tablename__ = "telemetry_readings"

    # BigInteger autoincrement primary key (with Integer variant for SQLite 64-bit ROWID compatibility)
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    sensor_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    humidity: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    raw_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_telemetry_sensor_timestamp", "sensor_id", "timestamp"),
    )
