"""0006_rack_cables

Revision ID: 0006_rack_cables
Revises: 0005_system_config_longtext
Create Date: 2026-11-25 09:10:00.000000

Cross-database migration (PostgreSQL, MySQL, MariaDB, SQLite) adding `rack_cables`
for port-to-port structured cabling and NetBox-style end-to-end Cable Trace.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0006_rack_cables"
down_revision: Union[str, None] = "0005_system_config_longtext"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rack_cables",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("label", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("cable_type", sa.String(length=32), nullable=False, server_default="fiber"),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="connected"),
        sa.Column("color", sa.String(length=32), nullable=False, server_default="#22c55e"),
        sa.Column("length_m", sa.Float(), nullable=True),
        sa.Column("a_rack_id", sa.String(length=36), sa.ForeignKey("racks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("a_device_id", sa.String(length=36), sa.ForeignKey("rack_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("a_port", sa.String(length=80), nullable=False, server_default="eth0"),
        sa.Column("a_port_side", sa.String(length=16), nullable=False, server_default="front"),
        sa.Column("b_rack_id", sa.String(length=36), sa.ForeignKey("racks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("b_device_id", sa.String(length=36), sa.ForeignKey("rack_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("b_port", sa.String(length=80), nullable=False, server_default="eth0"),
        sa.Column("b_port_side", sa.String(length=16), nullable=False, server_default="front"),
        sa.Column("building_cable_group_id", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_rack_cables_a_rack_id", "rack_cables", ["a_rack_id"])
    op.create_index("ix_rack_cables_a_device_id", "rack_cables", ["a_device_id"])
    op.create_index("ix_rack_cables_b_rack_id", "rack_cables", ["b_rack_id"])
    op.create_index("ix_rack_cables_b_device_id", "rack_cables", ["b_device_id"])
    op.create_index("ix_rack_cables_building_cable_group_id", "rack_cables", ["building_cable_group_id"])


def downgrade() -> None:
    op.drop_index("ix_rack_cables_building_cable_group_id", table_name="rack_cables")
    op.drop_index("ix_rack_cables_b_device_id", table_name="rack_cables")
    op.drop_index("ix_rack_cables_b_rack_id", table_name="rack_cables")
    op.drop_index("ix_rack_cables_a_device_id", table_name="rack_cables")
    op.drop_index("ix_rack_cables_a_rack_id", table_name="rack_cables")
    op.drop_table("rack_cables")
