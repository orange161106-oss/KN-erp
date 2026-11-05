"""Add requirement_request_batches, requirement_requests tables and requests permission columns.

Revision ID: c005_requirement_requests
Revises: 190996207995
Create Date: 2026-10-17 18:40:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c005_requirement_requests'
down_revision: Union[str, Sequence[str], None] = '190996207995'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. requirement_request_batches table
    op.create_table(
        'requirement_request_batches',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('planning_month', sa.Integer(), nullable=False),
        sa.Column('planning_year', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('source_code', sa.String(length=32), nullable=False),
        sa.Column('source_filename', sa.String(length=255), nullable=False),
        sa.Column('sheet_name', sa.String(length=128), nullable=True),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='ACTIVE', nullable=False),
        sa.Column('row_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('valid_row_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error_row_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('validation_summary', sa.JSON(), nullable=True),
        sa.Column('uploaded_by', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_req_batch_period', 'requirement_request_batches', ['planning_year', 'planning_month'])
    op.create_index('ix_req_batch_source', 'requirement_request_batches', ['planning_year', 'planning_month', 'source_code'])

    # 2. requirement_requests table
    op.create_table(
        'requirement_requests',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('planning_month', sa.Integer(), nullable=False),
        sa.Column('planning_year', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('source_code', sa.String(length=32), nullable=False),
        sa.Column('consumable_id', sa.Uuid(), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column('unit', sa.String(length=32), nullable=False),
        sa.Column('import_batch_id', sa.Uuid(), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='ACTIVE', nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['consumable_id'], ['consumables.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['import_batch_id'], ['requirement_request_batches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('planning_year', 'planning_month', 'source_code', 'consumable_id', 'import_batch_id', name='uq_req_requests_period_source_consumable_batch')
    )
    op.create_index('ix_req_requests_period_source', 'requirement_requests', ['planning_year', 'planning_month', 'source_code', 'status'])
    op.create_index('ix_req_requests_consumable', 'requirement_requests', ['consumable_id'])
    op.create_index('ix_req_requests_batch', 'requirement_requests', ['import_batch_id'])

    # 3. Add requests permission columns to users table
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_cols = {col['name'] for col in insp.get_columns('users')}
    
    if 'requests_read' not in existing_cols:
        op.add_column('users', sa.Column('requests_read', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    if 'requests_create' not in existing_cols:
        op.add_column('users', sa.Column('requests_create', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    if 'requests_update' not in existing_cols:
        op.add_column('users', sa.Column('requests_update', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    if 'requests_delete' not in existing_cols:
        op.add_column('users', sa.Column('requests_delete', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    op.drop_index('ix_req_requests_batch', table_name='requirement_requests')
    op.drop_index('ix_req_requests_consumable', table_name='requirement_requests')
    op.drop_index('ix_req_requests_period_source', table_name='requirement_requests')
    op.drop_table('requirement_requests')

    op.drop_index('ix_req_batch_source', table_name='requirement_request_batches')
    op.drop_index('ix_req_batch_period', table_name='requirement_request_batches')
    op.drop_table('requirement_request_batches')

    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing_cols = {col['name'] for col in insp.get_columns('users')}
    
    if 'requests_delete' in existing_cols:
        op.drop_column('users', 'requests_delete')
    if 'requests_update' in existing_cols:
        op.drop_column('users', 'requests_update')
    if 'requests_create' in existing_cols:
        op.drop_column('users', 'requests_create')
    if 'requests_read' in existing_cols:
        op.drop_column('users', 'requests_read')

