from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import Boolean, DateTime, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base, TimestampMixin, generate_uuid


class DataSource(Base, TimestampMixin):
    """External data ingestion source (MQTT, Webhook, HTTP Polling)."""
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 'mqtt', 'webhook', 'http_poll'
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_polled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[Optional[str]] = mapped_column(String(50), default="idle")
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
