"""0003_sensors_and_telemetry

Revision ID: 0003_sensors_and_telemetry
Revises: 0002_floor_plans_and_objects
Create Date: 2026-11-10 14:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0003_sensors_and_telemetry'
down_revision: Union[str, None] = '0002_floor_plans_and_objects'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. data_sources
    op.create_table(
        'data_sources',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('source_type', sa.String(length=50), nullable=False),
        sa.Column('config', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('last_polled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_status', sa.String(length=50), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 2. sensors
    op.create_table(
        'sensors',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('object_id', sa.String(length=36), sa.ForeignKey('placed_objects.id', ondelete='SET NULL'), nullable=True),
        sa.Column('data_source_id', sa.String(length=36), sa.ForeignKey('data_sources.id', ondelete='SET NULL'), nullable=True),
        sa.Column('identifier', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('sensor_type', sa.String(length=50), nullable=False, server_default='thermohygrometer'),
        sa.Column('temp_min_critical', sa.Float(), nullable=True),
        sa.Column('temp_min_warning', sa.Float(), nullable=True),
        sa.Column('temp_max_warning', sa.Float(), nullable=True),
        sa.Column('temp_max_critical', sa.Float(), nullable=True),
        sa.Column('humidity_min_critical', sa.Float(), nullable=True),
        sa.Column('humidity_min_warning', sa.Float(), nullable=True),
        sa.Column('humidity_max_warning', sa.Float(), nullable=True),
        sa.Column('humidity_max_critical', sa.Float(), nullable=True),
        sa.Column('current_temperature', sa.Float(), nullable=True),
        sa.Column('current_humidity', sa.Float(), nullable=True),
        sa.Column('battery_level', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='offline'),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_discovered', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f('ix_sensors_identifier'), 'sensors', ['identifier'], unique=True)
    op.create_index(op.f('ix_sensors_object_id'), 'sensors', ['object_id'], unique=False)
    op.create_index(op.f('ix_sensors_data_source_id'), 'sensors', ['data_source_id'], unique=False)

    # 3. alerts
    op.create_table(
        'alerts',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('sensor_id', sa.String(length=36), sa.ForeignKey('sensors.id', ondelete='CASCADE'), nullable=False),
        sa.Column('metric_type', sa.String(length=50), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('reading_value', sa.Float(), nullable=False),
        sa.Column('threshold_value', sa.Float(), nullable=False),
        sa.Column('message', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='active'),
        sa.Column('acknowledged_by', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f('ix_alerts_sensor_id'), 'alerts', ['sensor_id'], unique=False)
    op.create_index(op.f('ix_alerts_status'), 'alerts', ['status'], unique=False)


def downgrade() -> None:
    op.drop_table('alerts')
    op.drop_table('sensors')
    op.drop_table('data_sources')

