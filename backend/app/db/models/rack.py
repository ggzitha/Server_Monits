"""
rack.py - Single-source-of-truth SQLAlchemy models for Racks (4U-70U), Mounted Rack Devices,
and Reusable Device Library Templates (including NetBox-imported device types).
"""
from typing import List, Optional
from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin, generate_uuid


class Rack(Base, TimestampMixin):
    __tablename__ = "racks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    furniture_id: Mapped[Optional[str]] = mapped_column(String(100), index=True, unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="Server Rack")
    floor_id: Mapped[str] = mapped_column(String(64), nullable=False, default="ground", index=True)
    room_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Physical rack dimensions (4U to 70U, standard 19" or custom width, depth in mm)
    u_height: Mapped[int] = mapped_column(Integer, nullable=False, default=42)
    width_in: Mapped[float] = mapped_column(Float, nullable=False, default=19.0)
    depth_mm: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    color: Mapped[str] = mapped_column(String(32), nullable=False, default="#1e293b")

    # Floor-plan coordinates (meters) synchronized with 2D & 3D building state
    pos_x: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    pos_z: Mapped[float] = mapped_column(Float, nullable=False, default=2.0)
    rotation: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    max_power_w: Mapped[float] = mapped_column(Float, nullable=False, default=5000.0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    devices: Mapped[List["RackDevice"]] = relationship(
        "RackDevice",
        back_populates="rack",
        cascade="all, delete-orphan",
        order_by="RackDevice.u_position",
    )


class RackDevice(Base, TimestampMixin):
    __tablename__ = "rack_devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    rack_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("racks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # server, switch, patch_panel, pdu, ups, storage, blank_panel, custom
    device_type: Mapped[str] = mapped_column(String(40), nullable=False, default="server")
    manufacturer: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="")

    # Elevation placement (1-indexed bottom U slot)
    u_height: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    u_position: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    face: Mapped[str] = mapped_column(String(16), nullable=False, default="front")  # front | rear | both
    is_full_depth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    half_width: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    half_slot: Mapped[str] = mapped_column(String(16), nullable=False, default="full")  # full | left | right

    power_w: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="active")  # active | planned | offline | maintenance
    serial: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    color: Mapped[str] = mapped_column(String(32), nullable=False, default="#0284c7")
    slug: Mapped[str] = mapped_column(String(140), nullable=False, default="")
    front_image: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    rear_image: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ports_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    rack: Mapped["Rack"] = relationship("Rack", back_populates="devices")


class RackDeviceTemplate(Base, TimestampMixin):
    __tablename__ = "rack_device_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    device_type: Mapped[str] = mapped_column(String(40), nullable=False, default="server")
    manufacturer: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    slug: Mapped[str] = mapped_column(String(140), nullable=False, default="")
    u_height: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_full_depth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    half_width: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    power_w: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    color: Mapped[str] = mapped_column(String(32), nullable=False, default="#0284c7")
    front_image: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    rear_image: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
