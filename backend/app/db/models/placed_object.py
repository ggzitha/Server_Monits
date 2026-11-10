from datetime import datetime
from typing import Optional
from sqlalchemy import Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin, generate_uuid


class PlacedObject(Base, TimestampMixin):
    __tablename__ = "placed_objects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    floor_plan_id: Mapped[str] = mapped_column(String(36), ForeignKey("floor_plans.id", ondelete="CASCADE"), index=True, nullable=False)
    room_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    
    # Object category: "wall", "door", "window", "rack", "sensor", "camera", "ap", "lock", "tray"
    object_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(100), default="Object", nullable=False)
    
    # 3D Coordinates in decimal meters
    position_x: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    position_y: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    position_z: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # 3D Rotation in radians or degrees
    rotation_x: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rotation_y: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rotation_z: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Scale / dimensions in decimal meters (width, height, depth)
    scale_x: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    scale_y: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    scale_z: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    # Custom properties: color, wall endpoints, linked hardware, etc.
    properties: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    floor_plan: Mapped["FloorPlan"] = relationship("FloorPlan", back_populates="objects")
    room: Mapped[Optional["Room"]] = relationship("Room", back_populates="objects")

