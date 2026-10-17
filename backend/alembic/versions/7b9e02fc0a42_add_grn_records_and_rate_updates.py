"""add grn records and rate updates

Revision ID: 7b9e02fc0a42
Revises: 6a8f91eb9f31
Create Date: 2026-10-16 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7b9e02fc0a42'
down_revision: Union[str, Sequence[str], None] = '6a8f91eb9f31'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = set(insp.get_table_names())

    # 1. Create grn_records table
    if 'grn_records' not in tables:
        op.create_table(
            'grn_records',
            sa.Column('id', sa.Uuid(), primary_key=True),
            sa.Column('grn_no', sa.String(128), nullable=False),
            sa.Column('grn_date', sa.DateTime(timezone=True), nullable=True),
            sa.Column('vendor_name', sa.String(255), nullable=True),
            sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column('uploaded_by', sa.Uuid(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        )
        op.create_index('ix_grn_records_grn_no', 'grn_records', ['grn_no'])

    # 2. Create grn_line_items table
    if 'grn_line_items' not in tables:
        op.create_table(
            'grn_line_items',
            sa.Column('id', sa.Uuid(), primary_key=True),
            sa.Column('grn_id', sa.Uuid(), sa.ForeignKey('grn_records.id', ondelete='CASCADE'), nullable=False),
            sa.Column('consumable_id', sa.Uuid(), sa.ForeignKey('consumables.id', ondelete='SET NULL'), nullable=True),
            sa.Column('item_code', sa.String(128), nullable=False),
            sa.Column('received_qty', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('unit_rate', sa.Float(), nullable=False, server_default='0.0'),
            sa.Column('total_amount', sa.Float(), nullable=False, server_default='0.0'),
        )
        op.create_index('ix_grn_line_items_grn_id', 'grn_line_items', ['grn_id'])
        op.create_index('ix_grn_line_items_consumable_id', 'grn_line_items', ['consumable_id'])
        op.create_index('ix_grn_line_items_item_code', 'grn_line_items', ['item_code'])

    # 3. Add latest_grn_rate to consumables
    consumable_cols = {c['name'] for c in insp.get_columns('consumables')}
    if 'latest_grn_rate' not in consumable_cols:
        op.add_column(
            'consumables',
            sa.Column('latest_grn_rate', sa.Numeric(14, 4), nullable=True, server_default='0.0')
        )

    # 4. Add rate, receipt_qty, receipt_value to requirement_line_items
    req_cols = {c['name'] for c in insp.get_columns('requirement_line_items')}
    if 'rate' not in req_cols:
        op.add_column(
            'requirement_line_items',
            sa.Column('rate', sa.Float(), nullable=False, server_default='0.0')
        )
    if 'receipt_qty' not in req_cols:
        op.add_column(
            'requirement_line_items',
            sa.Column('receipt_qty', sa.Float(), nullable=False, server_default='0.0')
        )
    if 'receipt_value' not in req_cols:
        op.add_column(
            'requirement_line_items',
            sa.Column('receipt_value', sa.Float(), nullable=False, server_default='0.0')
        )


def downgrade() -> None:
    op.drop_column('requirement_line_items', 'receipt_value')
    op.drop_column('requirement_line_items', 'receipt_qty')
    op.drop_column('requirement_line_items', 'rate')
    op.drop_column('consumables', 'latest_grn_rate')
    op.drop_table('grn_line_items')
    op.drop_table('grn_records')
