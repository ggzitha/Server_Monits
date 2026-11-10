from datetime import datetime
from typing import List, Optional
from sqlalchemy import Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin, generate_uuid


class FloorPlan(Base, TimestampMixin):
    __tablename__ = "floor_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    site_name: Mapped[str] = mapped_column(String(100), default="Main Data Center", nullable=False)
    level_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    grid_size_meters: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    scale_ratio: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    rooms: Mapped[List["Room"]] = relationship(
        "Room",
        back_populates="floor_plan",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    objects: Mapped[List["PlacedObject"]] = relationship(
        "PlacedObject",
        back_populates="floor_plan",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Room(Base, TimestampMixin):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    floor_plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("floor_plans.id", ondelete="CASCADE"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), default="Server Room", nullable=False)
    # List of 2D polygon vertices in meters: [[x0, z0], [x1, z1], ...]
    polygon_points: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    wall_height_m: Mapped[float] = mapped_column(Float, default=3.0, nullable=False)
    wall_thickness_m: Mapped[float] = mapped_column(Float, default=0.2, nullable=False)
    floor_color: Mapped[str] = mapped_column(String(30), default="#0e1424", nullable=False)
    wall_color: Mapped[str] = mapped_column(String(30), default="#00f0ff", nullable=False)

    floor_plan: Mapped["FloorPlan"] = relationship("FloorPlan", back_populates="rooms")
    objects: Mapped[List["PlacedObject"]] = relationship("PlacedObject", back_populates="room")

