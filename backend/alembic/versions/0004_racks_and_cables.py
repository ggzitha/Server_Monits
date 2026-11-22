"""0004_racks_and_cables

Revision ID: 0004_racks_and_cables
Revises: 0003_sensors_and_telemetry
Create Date: 2026-11-22 11:00:00.000000

Cross-database migration (PostgreSQL, MySQL, MariaDB, SQLite) adding:
- racks (4U-70U rack definitions linked to 2D/3D floor-plan furniture_id)
- rack_devices (mounted devices with U position, height, face, half-width, power, status)
- rack_device_templates (built-in + user + NetBox-imported device library templates)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004_racks_and_cables"
down_revision: Union[str, None] = "0003_sensors_and_telemetry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "racks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("furniture_id", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("floor_id", sa.String(length=64), nullable=False, server_default="ground"),
        sa.Column("room_id", sa.String(length=100), nullable=True),
        sa.Column("u_height", sa.Integer(), nullable=False, server_default="42"),
        sa.Column("width_in", sa.Float(), nullable=False, server_default="19.0"),
        sa.Column("depth_mm", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("color", sa.String(length=32), nullable=False, server_default="#1e293b"),
        sa.Column("pos_x", sa.Float(), nullable=False, server_default="2.0"),
        sa.Column("pos_z", sa.Float(), nullable=False, server_default="2.0"),
        sa.Column("rotation", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("max_power_w", sa.Float(), nullable=False, server_default="5000.0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_racks_furniture_id"), "racks", ["furniture_id"], unique=True)
    op.create_index(op.f("ix_racks_floor_id"), "racks", ["floor_id"], unique=False)

    op.create_table(
        "rack_devices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("rack_id", sa.String(length=36), sa.ForeignKey("racks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("device_type", sa.String(length=40), nullable=False, server_default="server"),
        sa.Column("manufacturer", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("u_height", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("u_position", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("face", sa.String(length=16), nullable=False, server_default="front"),
        sa.Column("is_full_depth", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("half_width", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("half_slot", sa.String(length=16), nullable=False, server_default="full"),
        sa.Column("power_w", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="active"),
        sa.Column("serial", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("color", sa.String(length=32), nullable=False, server_default="#0284c7"),
        sa.Column("slug", sa.String(length=140), nullable=False, server_default=""),
        sa.Column("front_image", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("rear_image", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("ports_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_rack_devices_rack_id"), "rack_devices", ["rack_id"], unique=False)

    op.create_table(
        "rack_device_templates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("device_type", sa.String(length=40), nullable=False, server_default="server"),
        sa.Column("manufacturer", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("slug", sa.String(length=140), nullable=False, server_default=""),
        sa.Column("u_height", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_full_depth", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("half_width", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("power_w", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("color", sa.String(length=32), nullable=False, server_default="#0284c7"),
        sa.Column("front_image", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("rear_image", sa.String(length=300), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("rack_device_templates")
    op.drop_table("rack_devices")
    op.drop_table("racks")
