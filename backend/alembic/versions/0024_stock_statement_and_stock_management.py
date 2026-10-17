"""Add stock statement and stock parameter tables.

Revision ID: 0024_stock_statement_and_stock_management
Revises: 0023_customer_aliases_and_sales_schedule
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0024_stock_statement_and_stock_management'
down_revision: Union[str, Sequence[str], None] = '0023_customer_aliases_and_sales_schedule'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. Create stock_statement_batches table
    if 'stock_statement_batches' not in tables:
        op.create_table(
            'stock_statement_batches',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('statement_month', sa.Integer(), nullable=False),
            sa.Column('statement_year', sa.Integer(), nullable=False),
            sa.Column('statement_date', sa.Date(), nullable=False),
            sa.Column('source_filename', sa.String(255), nullable=False),
            sa.Column('file_hash', sa.String(64), nullable=False),
            sa.Column('status', sa.String(32), nullable=False, server_default='active'),
            sa.Column('row_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('warning_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('validation_summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        )
        op.create_index(
            'ix_stock_statement_batches_period',
            'stock_statement_batches',
            ['statement_year', 'statement_month']
        )
        op.create_index(
            'uq_stock_statement_batches_active_period',
            'stock_statement_batches',
            ['statement_year', 'statement_month'],
            unique=True,
            postgresql_where=sa.text("status = 'active'")
        )

    # 2. Create stock_statement_lines table
    if 'stock_statement_lines' not in tables:
        op.create_table(
            'stock_statement_lines',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('batch_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('stock_statement_batches.id', ondelete='CASCADE'), nullable=False),
            sa.Column('item_id', sa.String(128), nullable=False),
            sa.Column('consumable_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('consumables.id', ondelete='SET NULL'), nullable=True),
            sa.Column('item_description', sa.Text(), nullable=True),
            sa.Column('cust_part_no', sa.String(128), nullable=True),
            sa.Column('unit', sa.String(32), nullable=True),
            sa.Column('opening_qty', sa.Numeric(14, 4), nullable=True),
            sa.Column('opening_value', sa.Numeric(16, 4), nullable=True),
            sa.Column('receipt_qty', sa.Numeric(14, 4), nullable=True),
            sa.Column('receipt_value', sa.Numeric(16, 4), nullable=True),
            sa.Column('issue_qty', sa.Numeric(14, 4), nullable=True),
            sa.Column('issue_value', sa.Numeric(16, 4), nullable=True),
            sa.Column('closing_qty', sa.Numeric(14, 4), nullable=True),
            sa.Column('closing_value', sa.Numeric(16, 4), nullable=True),
            sa.Column('source_row', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('warning_codes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index('ix_stock_statement_lines_batch_id', 'stock_statement_lines', ['batch_id'])
        op.create_index('ix_stock_statement_lines_item_id', 'stock_statement_lines', ['item_id'])
        op.create_index('ix_stock_statement_lines_consumable_id', 'stock_statement_lines', ['consumable_id'])
        op.create_index('uq_stock_statement_lines_batch_item', 'stock_statement_lines', ['batch_id', 'item_id'], unique=True)

    # 3. Create stock_parameter_batches table
    if 'stock_parameter_batches' not in tables:
        op.create_table(
            'stock_parameter_batches',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('month', sa.Integer(), nullable=False),
            sa.Column('year', sa.Integer(), nullable=False),
            sa.Column('effective_date', sa.Date(), nullable=False),
            sa.Column('source_filename', sa.String(255), nullable=False),
            sa.Column('file_hash', sa.String(64), nullable=False),
            sa.Column('status', sa.String(32), nullable=False, server_default='active'),
            sa.Column('row_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('summary', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column('uploaded_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        )
        op.create_index(
            'ix_stock_parameter_batches_period',
            'stock_parameter_batches',
            ['year', 'month']
        )
        op.create_index(
            'uq_stock_parameter_batches_active_period',
            'stock_parameter_batches',
            ['year', 'month'],
            unique=True,
            postgresql_where=sa.text("status = 'active'")
        )

    # 4. Create stock_parameters table
    if 'stock_parameters' not in tables:
        op.create_table(
            'stock_parameters',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column('batch_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('stock_parameter_batches.id', ondelete='CASCADE'), nullable=False),
            sa.Column('item_id', sa.String(128), nullable=False),
            sa.Column('consumable_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('consumables.id', ondelete='SET NULL'), nullable=True),
            sa.Column('category', sa.String(128), nullable=True),
            sa.Column('type_of_material', sa.String(128), nullable=True),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('min_stock_level', sa.Numeric(14, 4), nullable=True),
            sa.Column('max_stock_level', sa.Numeric(14, 4), nullable=True),
            sa.Column('min_order_qty', sa.Numeric(14, 4), nullable=True),
            sa.Column('lead_time_days', sa.Integer(), nullable=True),
            sa.Column('edited_after_import', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('source_row', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        )
        op.create_index('ix_stock_parameters_batch_id', 'stock_parameters', ['batch_id'])
        op.create_index('ix_stock_parameters_item_id', 'stock_parameters', ['item_id'])
        op.create_index('ix_stock_parameters_consumable_id', 'stock_parameters', ['consumable_id'])
        op.create_index('uq_stock_parameters_batch_item', 'stock_parameters', ['batch_id', 'item_id'], unique=True)


def downgrade() -> None:
    op.drop_table('stock_parameters')
    op.drop_table('stock_parameter_batches')
    op.drop_table('stock_statement_lines')
    op.drop_table('stock_statement_batches')

