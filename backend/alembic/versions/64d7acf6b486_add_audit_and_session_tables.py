"""Add audit and session tables

Revision ID: 64d7acf6b486
Revises: e001_phase4_product_master_pipeline
Create Date: 2026-10-12 00:33:53.028314
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '64d7acf6b486'
down_revision: Union[str, Sequence[str], None] = 'e001_phase4_product_master_pipeline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create user_sessions table
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('ip_address', sa.String(length=64), nullable=True),
        sa.Column('login_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('logout_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('status', sa.String(length=32), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_sessions_user_id_users'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_user_sessions')),
    )
    op.create_index(op.f('ix_user_sessions_status'), 'user_sessions', ['status'], unique=False)
    op.create_index(op.f('ix_user_sessions_user_id'), 'user_sessions', ['user_id'], unique=False)

    # 2. Update audit_logs table
    op.add_column('audit_logs', sa.Column('user_id', sa.Uuid(), nullable=True))
    op.add_column('audit_logs', sa.Column('username', sa.String(length=128), nullable=True))
    op.add_column('audit_logs', sa.Column('module', sa.String(length=128), nullable=True))
    op.add_column('audit_logs', sa.Column('record_id', sa.String(length=256), nullable=True))
    op.add_column('audit_logs', sa.Column('changes_summary', sa.JSON(), nullable=True))
    op.add_column('audit_logs', sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False))
    op.alter_column('audit_logs', 'action',
               existing_type=sa.VARCHAR(length=32),
               type_=sa.String(length=64),
               existing_nullable=False)
    op.alter_column('audit_logs', 'actor_id',
               existing_type=sa.UUID(),
               nullable=True)
    op.alter_column('audit_logs', 'entity_type',
               existing_type=sa.VARCHAR(length=64),
               nullable=True)
    op.alter_column('audit_logs', 'entity_id',
               existing_type=sa.UUID(),
               nullable=True)
    op.alter_column('audit_logs', 'new_values',
               existing_type=postgresql.JSON(astext_type=sa.Text()),
               nullable=True)
    op.alter_column('audit_logs', 'reason',
               existing_type=sa.TEXT(),
               nullable=True)
    op.alter_column('audit_logs', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=True,
               existing_server_default=sa.text('now()'))
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_module'), 'audit_logs', ['module'], unique=False)
    op.create_index(op.f('ix_audit_logs_record_id'), 'audit_logs', ['record_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_timestamp'), 'audit_logs', ['timestamp'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)
    op.create_index(op.f('ix_audit_logs_username'), 'audit_logs', ['username'], unique=False)
    op.create_foreign_key(op.f('fk_audit_logs_user_id_users'), 'audit_logs', 'users', ['user_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    # 1. Downgrade audit_logs
    op.drop_constraint(op.f('fk_audit_logs_user_id_users'), 'audit_logs', type_='foreignkey')
    op.drop_index(op.f('ix_audit_logs_username'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_user_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_timestamp'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_record_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_module'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.alter_column('audit_logs', 'created_at',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               nullable=False,
               existing_server_default=sa.text('now()'))
    op.alter_column('audit_logs', 'reason',
               existing_type=sa.TEXT(),
               nullable=False)
    op.alter_column('audit_logs', 'new_values',
               existing_type=postgresql.JSON(astext_type=sa.Text()),
               nullable=False)
    op.alter_column('audit_logs', 'entity_id',
               existing_type=sa.UUID(),
               nullable=False)
    op.alter_column('audit_logs', 'entity_type',
               existing_type=sa.VARCHAR(length=64),
               nullable=False)
    op.alter_column('audit_logs', 'actor_id',
               existing_type=sa.UUID(),
               nullable=False)
    op.alter_column('audit_logs', 'action',
               existing_type=sa.String(length=64),
               type_=sa.VARCHAR(length=32),
               existing_nullable=False)
    op.drop_column('audit_logs', 'timestamp')
    op.drop_column('audit_logs', 'changes_summary')
    op.drop_column('audit_logs', 'record_id')
    op.drop_column('audit_logs', 'module')
    op.drop_column('audit_logs', 'username')
    op.drop_column('audit_logs', 'user_id')

    # 2. Downgrade user_sessions
    op.drop_index(op.f('ix_user_sessions_user_id'), table_name='user_sessions')
    op.drop_index(op.f('ix_user_sessions_status'), table_name='user_sessions')
    op.drop_table('user_sessions')
