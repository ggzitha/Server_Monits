"""
security.py - Single-source-of-truth SQLAlchemy models for Phase 6 Security Devices:
- SecurityDevice: CCTV cameras (with 3D FOV cones & stream/snapshot URLs), door access /
  biometric fingerprint readers, motion sensors, and door/rack contact sensors.
- SecurityEvent: Access logs, motion triggers, door forced/opened events, and alert acknowledgments.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin, generate_uuid


class SecurityDevice(Base, TimestampMixin):
    __tablename__ = "security_devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    entity_id: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    # cctv | door_access | fingerprint | motion | contact
    device_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="cctv", index=True)

    # 2D/3D Floor-plan placement
    floor_id: Mapped[str] = mapped_column(String(64), nullable=False, default="ground", index=True)
    room_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pos_x: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)
    pos_z: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    pos_y: Mapped[float] = mapped_column(Float, nullable=False, default=2.8)
    rotation: Mapped[float] = mapped_column(Float, nullable=False, default=180.0)

    # Camera / 3D FOV Cone & Stream fields
    fov_deg: Mapped[float] = mapped_column(Float, nullable=False, default=75.0)
    reach_m: Mapped[float] = mapped_column(Float, nullable=False, default=7.0)
    cone_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    stream_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    snapshot_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")

    # Live operational state & alerting
    # cctv: recording | streaming | idle | offline
    # door_access / fingerprint: locked | unlocked
    # motion: clear | detected
    # contact: closed | open
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="recording")
    armed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    alert_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    alert_message: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    last_event_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    config_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, default=dict, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    events: Mapped[List["SecurityEvent"]] = relationship(
        "SecurityEvent",
        back_populates="device",
        cascade="all, delete-orphan",
        order_by="SecurityEvent.created_at.desc()",
    )


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    device_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("security_devices.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # access_granted | access_denied | door_opened | door_closed | door_forced |
    # motion_detected | motion_cleared | camera_alert | lock_toggled | alert_ack
    event_type: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    # info | warning | critical
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="info", index=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    message: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    device: Mapped["SecurityDevice"] = relationship("SecurityDevice", back_populates="events")
