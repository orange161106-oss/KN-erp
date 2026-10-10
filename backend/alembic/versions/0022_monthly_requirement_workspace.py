"""Add monthly requirement records workspace and planning version timestamps.

Revision ID: 0022_monthly_requirement_workspace
Revises: cd63eeb15edc
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0022_monthly_requirement_workspace'
down_revision: Union[str, Sequence[str], None] = 'cd63eeb15edc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Extend planning_versions table with modification tracking and month/year
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    pv_cols = [c['name'] for c in inspector.get_columns('planning_versions')]

    if 'updated_at' not in pv_cols:
        op.add_column('planning_versions', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    if 'updated_by' not in pv_cols:
        op.add_column('planning_versions', sa.Column('updated_by', sa.Uuid(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True))
    if 'planning_month' not in pv_cols:
        op.add_column('planning_versions', sa.Column('planning_month', sa.Integer(), nullable=True))
    if 'planning_year' not in pv_cols:
        op.add_column('planning_versions', sa.Column('planning_year', sa.Integer(), nullable=True))

    # 2. Create monthly_requirement_records table for spreadsheet-style planning
    op.create_table(
        'monthly_requirement_records',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('planning_version_id', sa.Uuid(), sa.ForeignKey('planning_versions.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('planning_period', sa.String(7), nullable=False, index=True),
        sa.Column('planning_month', sa.Integer(), nullable=False),
        sa.Column('planning_year', sa.Integer(), nullable=False),
        sa.Column('row_index', sa.Integer(), nullable=True),
        sa.Column('part_name', sa.String(255), nullable=False),
        sa.Column('part_number', sa.String(128), nullable=False),
        sa.Column('consumable_code', sa.String(64), nullable=False),
        sa.Column('consumable_name', sa.String(255), nullable=False),
        sa.Column('process_name', sa.String(128), nullable=False),
        sa.Column('part_thickness', sa.Numeric(10, 4), nullable=False, server_default='0'),
        sa.Column('process_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('production_order_qty', sa.Numeric(14, 4), nullable=False, server_default='0'),
        sa.Column('scheduled_consumable_qty', sa.Numeric(14, 4), nullable=False, server_default='0'),
        sa.Column('unit', sa.String(32), nullable=False, server_default='NOS'),
        sa.Column('plant', sa.String(64), nullable=False, server_default='Plant 1'),
        sa.Column('stock_qty', sa.Numeric(14, 4), nullable=False, server_default='0'),
        sa.Column('shortage_qty', sa.Numeric(14, 4), nullable=False, server_default='0'),
        sa.Column('po_pending_qty', sa.Numeric(14, 4), nullable=False, server_default='0'),
        sa.Column('msl', sa.Numeric(14, 4), nullable=False, server_default='0'),
        sa.Column('status', sa.String(64), nullable=False, server_default='DRAFT'),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_by', sa.Uuid(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        if_not_exists=True,
    )

    # Indices
    indices = [idx['name'] for idx in inspector.get_indexes('monthly_requirement_records')] if 'monthly_requirement_records' in inspector.get_table_names() else []
    if 'ix_monthly_req_period' not in indices:
        op.create_index('ix_monthly_req_period', 'monthly_requirement_records', ['planning_period'], if_not_exists=True)
    if 'ix_monthly_req_consumable' not in indices:
        op.create_index('ix_monthly_req_consumable', 'monthly_requirement_records', ['consumable_code'], if_not_exists=True)
    if 'ix_monthly_req_part' not in indices:
        op.create_index('ix_monthly_req_part', 'monthly_requirement_records', ['part_number'], if_not_exists=True)


def downgrade() -> None:
    op.drop_table('monthly_requirement_records')
    op.drop_column('planning_versions', 'planning_year')
    op.drop_column('planning_versions', 'planning_month')
    op.drop_column('planning_versions', 'updated_by')
    op.drop_column('planning_versions', 'updated_at')

