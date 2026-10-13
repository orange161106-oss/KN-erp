"""Add customer aliases and sales schedule planning columns.

Revision ID: 0023_customer_aliases_and_sales_schedule
Revises: 0022_monthly_requirement_workspace
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0023_customer_aliases_and_sales_schedule'
down_revision: Union[str, Sequence[str], None] = '0022_monthly_requirement_workspace'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. Create customer_aliases table if not exists
    if 'customer_aliases' not in tables:
        op.create_table(
            'customer_aliases',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('customer_id', sa.Uuid(), sa.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False),
            sa.Column('alias_text', sa.String(255), nullable=False),
            sa.Column('normalized_alias', sa.String(255), nullable=False),
            sa.Column('group_label', sa.String(128), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_customer_aliases')),
            sa.UniqueConstraint('normalized_alias', name=op.f('uq_customer_aliases_normalized_alias')),
        )
        op.create_index(op.f('ix_customer_aliases_customer_id'), 'customer_aliases', ['customer_id'])
        op.create_index(op.f('ix_customer_aliases_normalized_alias'), 'customer_aliases', ['normalized_alias'])

    # 2. Add columns to prd_records
    prd_cols = [c['name'] for c in inspector.get_columns('prd_records')]
    if 'customer_id' not in prd_cols:
        op.add_column('prd_records', sa.Column('customer_id', sa.Uuid(), sa.ForeignKey('customers.id', ondelete='SET NULL'), nullable=True))
    if 'customer_code' not in prd_cols:
        op.add_column('prd_records', sa.Column('customer_code', sa.String(64), nullable=True))
    if 'customer_group' not in prd_cols:
        op.add_column('prd_records', sa.Column('customer_group', sa.String(128), nullable=True))
    if 'source_customer_label' not in prd_cols:
        op.add_column('prd_records', sa.Column('source_customer_label', sa.String(255), nullable=True))
    if 'source_row' not in prd_cols:
        op.add_column('prd_records', sa.Column('source_row', sa.Integer(), nullable=True))
    if 'revision' not in prd_cols:
        op.add_column('prd_records', sa.Column('revision', sa.String(32), nullable=True))
    if 'schedule_given_on' not in prd_cols:
        op.add_column('prd_records', sa.Column('schedule_given_on', sa.DateTime(timezone=True), nullable=True))
    if 'plan_month' not in prd_cols:
        op.add_column('prd_records', sa.Column('plan_month', sa.Integer(), nullable=True))
    if 'plan_year' not in prd_cols:
        op.add_column('prd_records', sa.Column('plan_year', sa.Integer(), nullable=True))
    if 'section_type' not in prd_cols:
        op.add_column('prd_records', sa.Column('section_type', sa.String(32), server_default='STANDARD', nullable=True))

    # 3. Add columns to import_batches
    batch_cols = [c['name'] for c in inspector.get_columns('import_batches')]
    if 'file_hash' not in batch_cols:
        op.add_column('import_batches', sa.Column('file_hash', sa.String(64), nullable=True))
    if 'validation_summary' not in batch_cols:
        op.add_column('import_batches', sa.Column('validation_summary', sa.JSON(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # 1. Drop customer_aliases
    if 'customer_aliases' in inspector.get_table_names():
        op.drop_table('customer_aliases')

    # 2. Drop columns from prd_records
    prd_cols = [c['name'] for c in inspector.get_columns('prd_records')]
    for col in [
        'customer_id', 'customer_code', 'customer_group', 'source_customer_label',
        'source_row', 'revision', 'schedule_given_on', 'plan_month', 'plan_year', 'section_type'
    ]:
        if col in prd_cols:
            op.drop_column('prd_records', col)

    # 3. Drop columns from import_batches
    batch_cols = [c['name'] for c in inspector.get_columns('import_batches')]
    if 'file_hash' in batch_cols:
        op.drop_column('import_batches', 'file_hash')
    if 'validation_summary' in batch_cols:
        op.drop_column('import_batches', 'validation_summary')

