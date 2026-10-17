"""Update stock_parameters uniqueness to include category/type and add resolution columns.

Revision ID: 0026_stock_parameters_category_uniqueness_and_resolutions
Revises: 0025_add_item_class_to_stock_statement_lines
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0026_stock_parameters_category_uniqueness_and_resolutions'
down_revision: Union[str, Sequence[str], None] = '0025_add_item_class_to_stock_statement_lines'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c['name'] for c in inspector.get_columns('stock_parameters')]
    indexes = [idx['name'] for idx in inspector.get_indexes('stock_parameters')]

    # 1. Drop old item-only unique index so same item can appear under multiple categories
    if 'uq_stock_parameters_batch_item' in indexes:
        op.drop_index('uq_stock_parameters_batch_item', table_name='stock_parameters')

    # 2. Add resolution tracking columns if missing
    if 'resolution_applied' not in cols:
        op.add_column(
            'stock_parameters',
            sa.Column('resolution_applied', sa.String(64), nullable=True, server_default='NONE'),
        )
    if 'resolved_by' not in cols:
        op.add_column(
            'stock_parameters',
            sa.Column(
                'resolved_by',
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey('users.id', ondelete='SET NULL'),
                nullable=True,
            ),
        )
    if 'resolved_at' not in cols:
        op.add_column(
            'stock_parameters',
            sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        )
    if 'resolution_note' not in cols:
        op.add_column(
            'stock_parameters',
            sa.Column('resolution_note', sa.Text(), nullable=True),
        )

    # 3. Create composite index on (batch_id, item_id, category, type_of_material)
    if 'uq_stock_parameters_batch_item_cat_type' not in indexes:
        if conn.dialect.name == 'postgresql':
            op.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_stock_parameters_batch_item_cat_type
                ON stock_parameters (
                    batch_id,
                    UPPER(BTRIM(item_id)),
                    UPPER(BTRIM(COALESCE(category, ''))),
                    UPPER(BTRIM(COALESCE(type_of_material, '')))
                )
                """
            )
        else:
            op.create_index(
                'uq_stock_parameters_batch_item_cat_type',
                'stock_parameters',
                ['batch_id', 'item_id', 'category', 'type_of_material'],
                unique=True,
            )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    cols = [c['name'] for c in inspector.get_columns('stock_parameters')]
    indexes = [idx['name'] for idx in inspector.get_indexes('stock_parameters')]

    if 'uq_stock_parameters_batch_item_cat_type' in indexes:
        op.drop_index('uq_stock_parameters_batch_item_cat_type', table_name='stock_parameters')

    for col_name in ('resolution_note', 'resolved_at', 'resolved_by', 'resolution_applied'):
        if col_name in cols:
            op.drop_column('stock_parameters', col_name)

    if 'uq_stock_parameters_batch_item' not in indexes:
        op.create_index(
            'uq_stock_parameters_batch_item',
            'stock_parameters',
            ['batch_id', 'item_id'],
            unique=True,
        )

