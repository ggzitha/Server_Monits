"""0005_system_config_longtext

Revision ID: 0005_system_config_longtext
Revises: 0004_racks_and_cables
Create Date: 2026-11-23 12:00:00.000000

Upgrade system_config.value from TEXT (64 KB limit) to LONGTEXT (4 GB) on MySQL / MariaDB
so large 3D building JSON payloads and restore snapshots never hit Error 1406.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "0005_system_config_longtext"
down_revision: Union[str, None] = "0004_racks_and_cables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name in ("mysql", "mariadb"):
        op.alter_column(
            "system_config",
            "value",
            existing_type=sa.Text(),
            type_=mysql.LONGTEXT(),
            existing_nullable=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name in ("mysql", "mariadb"):
        op.alter_column(
            "system_config",
            "value",
            existing_type=mysql.LONGTEXT(),
            type_=sa.Text(),
            existing_nullable=False,
        )
