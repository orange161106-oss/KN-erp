"""Add item_class to stock_statement_lines.

Revision ID: 0025_add_item_class_to_stock_statement_lines
Revises: 0024_stock_statement_and_stock_management
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '0025_add_item_class_to_stock_statement_lines'
down_revision: Union[str, Sequence[str], None] = '0024_stock_statement_and_stock_management'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c['name'] for c in inspector.get_columns('stock_statement_lines')]
    if 'item_class' not in cols:
        op.add_column(
            'stock_statement_lines',
            sa.Column('item_class', sa.String(32), nullable=False, server_default='CONSUMABLE'),
        )
        op.create_index(
            'ix_stock_statement_lines_item_class',
            'stock_statement_lines',
            ['item_class'],
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c['name'] for c in inspector.get_columns('stock_statement_lines')]
    if 'item_class' in cols:
        op.drop_index('ix_stock_statement_lines_item_class', table_name='stock_statement_lines')
        op.drop_column('stock_statement_lines', 'item_class')

