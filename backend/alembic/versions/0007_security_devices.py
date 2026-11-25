"""0007_security_devices

Revision ID: 0007_security_devices
Revises: 0006_rack_cables
Create Date: 2026-11-25 10:00:00.000000

Cross-database migration (PostgreSQL, MySQL, MariaDB, SQLite) adding:
- security_devices (CCTV cameras with 3D cones & streams, door access/fingerprint, motion/contact sensors)
- security_events (access logs, motion/door alerts, acknowledgments)
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0007_security_devices"
down_revision: Union[str, None] = "0006_rack_cables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "security_devices",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("entity_id", sa.String(length=120), nullable=False, unique=True),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("device_kind", sa.String(length=32), nullable=False, server_default="cctv"),
        sa.Column("floor_id", sa.String(length=64), nullable=False, server_default="ground"),
        sa.Column("room_id", sa.String(length=100), nullable=True),
        sa.Column("pos_x", sa.Float(), nullable=False, server_default="3.0"),
        sa.Column("pos_z", sa.Float(), nullable=False, server_default="2.0"),
        sa.Column("pos_y", sa.Float(), nullable=False, server_default="2.8"),
        sa.Column("rotation", sa.Float(), nullable=False, server_default="180.0"),
        sa.Column("fov_deg", sa.Float(), nullable=False, server_default="75.0"),
        sa.Column("reach_m", sa.Float(), nullable=False, server_default="7.0"),
        sa.Column("cone_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("stream_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("snapshot_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("state", sa.String(length=32), nullable=False, server_default="recording"),
        sa.Column("armed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("alert_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("alert_message", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_security_devices_entity_id", "security_devices", ["entity_id"], unique=True)
    op.create_index("ix_security_devices_device_kind", "security_devices", ["device_kind"])
    op.create_index("ix_security_devices_floor_id", "security_devices", ["floor_id"])
    op.create_index("ix_security_devices_alert_active", "security_devices", ["alert_active"])

    op.create_table(
        "security_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("device_id", sa.String(length=36), sa.ForeignKey("security_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("actor", sa.String(length=120), nullable=False, server_default="system"),
        sa.Column("message", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("acknowledged_by", sa.String(length=120), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_security_events_device_id", "security_events", ["device_id"])
    op.create_index("ix_security_events_event_type", "security_events", ["event_type"])
    op.create_index("ix_security_events_severity", "security_events", ["severity"])
    op.create_index("ix_security_events_acknowledged", "security_events", ["acknowledged"])
    op.create_index("ix_security_events_created_at", "security_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("security_events")
    op.drop_table("security_devices")
