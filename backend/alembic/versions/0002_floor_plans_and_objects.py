"""0002_floor_plans_and_objects

Revision ID: 0002_floor_plans_and_objects
Revises: 0001_initial_schema
Create Date: 2026-11-10 13:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0002_floor_plans_and_objects'
down_revision: Union[str, None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. floor_plans
    op.create_table(
        'floor_plans',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('site_name', sa.String(length=100), nullable=False),
        sa.Column('level_index', sa.Integer(), nullable=False),
        sa.Column('grid_size_meters', sa.Float(), nullable=False),
        sa.Column('scale_ratio', sa.Float(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 2. rooms
    op.create_table(
        'rooms',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('floor_plan_id', sa.String(length=36), sa.ForeignKey('floor_plans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('polygon_points', sa.JSON(), nullable=False),
        sa.Column('wall_height_m', sa.Float(), nullable=False),
        sa.Column('wall_thickness_m', sa.Float(), nullable=False),
        sa.Column('floor_color', sa.String(length=30), nullable=False),
        sa.Column('wall_color', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f('ix_rooms_floor_plan_id'), 'rooms', ['floor_plan_id'], unique=False)

    # 3. placed_objects
    op.create_table(
        'placed_objects',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('floor_plan_id', sa.String(length=36), sa.ForeignKey('floor_plans.id', ondelete='CASCADE'), nullable=False),
        sa.Column('room_id', sa.String(length=36), sa.ForeignKey('rooms.id', ondelete='SET NULL'), nullable=True),
        sa.Column('object_type', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('position_x', sa.Float(), nullable=False),
        sa.Column('position_y', sa.Float(), nullable=False),
        sa.Column('position_z', sa.Float(), nullable=False),
        sa.Column('rotation_x', sa.Float(), nullable=False),
        sa.Column('rotation_y', sa.Float(), nullable=False),
        sa.Column('rotation_z', sa.Float(), nullable=False),
        sa.Column('scale_x', sa.Float(), nullable=False),
        sa.Column('scale_y', sa.Float(), nullable=False),
        sa.Column('scale_z', sa.Float(), nullable=False),
        sa.Column('properties', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f('ix_placed_objects_floor_plan_id'), 'placed_objects', ['floor_plan_id'], unique=False)
    op.create_index(op.f('ix_placed_objects_room_id'), 'placed_objects', ['room_id'], unique=False)


def downgrade() -> None:
    op.drop_table('placed_objects')
    op.drop_table('rooms')
    op.drop_table('floor_plans')

