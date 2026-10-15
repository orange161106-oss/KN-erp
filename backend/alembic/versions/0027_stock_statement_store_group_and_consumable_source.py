"""Add store_group to stock_statement_lines, location_text to stock_statement_batches, and source to consumables.

Revision ID: 0027_stock_statement_store_group_and_consumable_source
Revises: 0026_stock_parameters_category_uniqueness_and_resolutions, e001_phase4_product_master_pipeline
Create Date: 2026-10-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0027_stock_statement_store_group_and_consumable_source'
down_revision: Union[str, Sequence[str], None] = (
    '0026_stock_parameters_category_uniqueness_and_resolutions',
    'e001_phase4_product_master_pipeline',
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # 1. stock_statement_lines: add store_group
    ssl_cols = [c['name'] for c in inspector.get_columns('stock_statement_lines')]
    if 'store_group' not in ssl_cols:
        op.add_column('stock_statement_lines', sa.Column('store_group', sa.Text(), nullable=True))

    ssl_indexes = [idx['name'] for idx in inspector.get_indexes('stock_statement_lines')]
    if 'ix_stock_statement_lines_batch_item' not in ssl_indexes:
        op.create_index(
            'ix_stock_statement_lines_batch_item',
            'stock_statement_lines',
            ['batch_id', 'item_id'],
            unique=False,
        )

    # 2. stock_statement_batches: add location_text
    ssb_cols = [c['name'] for c in inspector.get_columns('stock_statement_batches')]
    if 'location_text' not in ssb_cols:
        op.add_column('stock_statement_batches', sa.Column('location_text', sa.String(255), nullable=True))

    # 3. consumables: add source
    cons_cols = [c['name'] for c in inspector.get_columns('consumables')]
    if 'source' not in cons_cols:
        op.add_column('consumables', sa.Column('source', sa.String(64), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    ssl_cols = [c['name'] for c in inspector.get_columns('stock_statement_lines')]
    if 'store_group' in ssl_cols:
        op.drop_column('stock_statement_lines', 'store_group')

    ssl_indexes = [idx['name'] for idx in inspector.get_indexes('stock_statement_lines')]
    if 'ix_stock_statement_lines_batch_item' in ssl_indexes:
        op.drop_index('ix_stock_statement_lines_batch_item', table_name='stock_statement_lines')

    ssb_cols = [c['name'] for c in inspector.get_columns('stock_statement_batches')]
    if 'location_text' in ssb_cols:
        op.drop_column('stock_statement_batches', 'location_text')

    cons_cols = [c['name'] for c in inspector.get_columns('consumables')]
    if 'source' in cons_cols:
        op.drop_column('consumables', 'source')
