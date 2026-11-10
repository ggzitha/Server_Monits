"""0001_initial_schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-11-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0001_initial_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. system_config
    op.create_table(
        'system_config',
        sa.Column('key', sa.String(length=64), primary_key=True),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 2. roles
    op.create_table(
        'roles',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('name', sa.String(length=50), nullable=False, unique=True),
        sa.Column('description', sa.String(length=255), nullable=False),
        sa.Column('permissions', sa.JSON(), nullable=False),
        sa.Column('is_system', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f('ix_roles_name'), 'roles', ['name'], unique=True)

    # 3. users
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('username', sa.String(length=50), nullable=False, unique=True),
        sa.Column('email', sa.String(length=255), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('is_totp_enabled', sa.Boolean(), nullable=False),
        sa.Column('preferred_lang', sa.String(length=10), nullable=False),
        sa.Column('preferred_theme', sa.String(length=20), nullable=False),
        sa.Column('failed_login_attempts', sa.Integer(), nullable=False),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)

    # 4. user_roles
    op.create_table(
        'user_roles',
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('role_id', sa.String(length=36), sa.ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True),
    )

    # 5. user_sessions
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_token', sa.String(length=128), nullable=False, unique=True),
        sa.Column('ip_address', sa.String(length=45), nullable=False),
        sa.Column('user_agent', sa.String(length=255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f('ix_user_sessions_session_token'), 'user_sessions', ['session_token'], unique=True)
    op.create_index(op.f('ix_user_sessions_user_id'), 'user_sessions', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_sessions_expires_at'), 'user_sessions', ['expires_at'], unique=False)

    # 6. refresh_tokens
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('token_hash', sa.String(length=128), nullable=False, unique=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f('ix_refresh_tokens_token_hash'), 'refresh_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_refresh_tokens_user_id'), 'refresh_tokens', ['user_id'], unique=False)

    # 7. api_tokens
    op.create_table(
        'api_tokens',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('token_hash', sa.String(length=128), nullable=False, unique=True),
        sa.Column('scopes', sa.JSON(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f('ix_api_tokens_token_hash'), 'api_tokens', ['token_hash'], unique=True)
    op.create_index(op.f('ix_api_tokens_user_id'), 'api_tokens', ['user_id'], unique=False)

    # 8. two_factor_secrets
    op.create_table(
        'two_factor_secrets',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('secret_encrypted', sa.Text(), nullable=False),
        sa.Column('recovery_codes_hash', sa.JSON(), nullable=False),
        sa.Column('is_confirmed', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 9. login_attempts (Database-backed lockout & rate limiting)
    op.create_table(
        'login_attempts',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('ip_address', sa.String(length=45), nullable=False),
        sa.Column('username', sa.String(length=100), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('attempted_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f('ix_login_attempts_ip_address'), 'login_attempts', ['ip_address'], unique=False)
    op.create_index(op.f('ix_login_attempts_username'), 'login_attempts', ['username'], unique=False)
    op.create_index(op.f('ix_login_attempts_attempted_at'), 'login_attempts', ['attempted_at'], unique=False)
    op.create_index('ix_login_attempt_ip_time', 'login_attempts', ['ip_address', 'attempted_at'], unique=False)
    op.create_index('ix_login_attempt_user_time', 'login_attempts', ['username', 'attempted_at'], unique=False)

    # 9. audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('resource_type', sa.String(length=64), nullable=False),
        sa.Column('resource_id', sa.String(length=64), nullable=True),
        sa.Column('details', sa.JSON(), nullable=False),
        sa.Column('ip_address', sa.String(length=45), nullable=False),
        sa.Column('user_agent', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)

    # 10. telemetry_readings
    op.create_table(
        'telemetry_readings',
        sa.Column('id', sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column('sensor_id', sa.String(length=36), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=True),
        sa.Column('humidity', sa.Float(), nullable=True),
        sa.Column('raw_data', sa.JSON(), nullable=True),
    )
    op.create_index('ix_telemetry_sensor_timestamp', 'telemetry_readings', ['sensor_id', 'timestamp'], unique=False)


def downgrade() -> None:
    op.drop_table('telemetry_readings')
    op.drop_table('audit_logs')
    op.drop_table('login_attempts')
    op.drop_table('two_factor_secrets')
    op.drop_table('api_tokens')
    op.drop_table('refresh_tokens')
    op.drop_table('user_sessions')
    op.drop_table('user_roles')
    op.drop_table('users')
    op.drop_table('roles')
    op.drop_table('system_config')

