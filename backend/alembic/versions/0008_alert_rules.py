"""0008_alert_rules

Revision ID: 0008_alert_rules
Revises: 0007_security_devices
Create Date: 2026-11-25 16:00:00.000000

Cross-database migration (PostgreSQL, MySQL, MariaDB, SQLite) adding `alert_rules`
for Phase 7 configurable threshold alerting & incident reporting.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0008_alert_rules"
down_revision: Union[str, None] = "0007_security_devices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("target_scope", sa.String(length=32), nullable=False, server_default="all_sensors"),
        sa.Column("target_id", sa.String(length=100), nullable=True),
        sa.Column("metric_type", sa.String(length=40), nullable=False, server_default="temperature"),
        sa.Column("operator", sa.String(length=12), nullable=False, server_default="gt"),
        sa.Column("warning_threshold", sa.Float(), nullable=True),
        sa.Column("critical_threshold", sa.Float(), nullable=False, server_default="30.0"),
        sa.Column("cooldown_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("notify_webhook_url", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alert_rules_enabled", "alert_rules", ["enabled"])
    op.create_index("ix_alert_rules_target_scope", "alert_rules", ["target_scope"])


def downgrade() -> None:
    op.drop_table("alert_rules")
