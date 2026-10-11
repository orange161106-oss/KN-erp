"""Phase 4 Product Master Re-Architecture and Excel Pipeline

Revision ID: e001_phase4_product_master_pipeline
Revises: cd63eeb15edc
Create Date: 2026-10-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e001_phase4_product_master_pipeline'
down_revision: Union[str, Sequence[str], None] = 'cd63eeb15edc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update consumables table
    # Drop old check constraint if exists
    try:
        op.drop_constraint('normalized_code', 'consumables', type_='check')
    except Exception:
        pass
    
    # Rename code to item_id
    op.alter_column('consumables', 'code', new_column_name='item_id', existing_type=sa.String(64), type_=sa.String(128))
    
    # Add new unique constraint & check constraint on item_id
    op.create_unique_constraint('uq_consumables_item_id', 'consumables', ['item_id'])
    op.create_check_constraint('normalized_item_id', 'consumables', "item_id = upper(btrim(item_id)) AND length(item_id) > 0")

    # Add extra metadata columns for consumables
    op.add_column('consumables', sa.Column('supplier_id', sa.Uuid(), sa.ForeignKey('suppliers.id', ondelete='SET NULL'), nullable=True))
    op.add_column('consumables', sa.Column('supplier_name', sa.String(255), nullable=True))
    op.add_column('consumables', sa.Column('category', sa.String(128), nullable=True))
    op.add_column('consumables', sa.Column('type_of_material', sa.String(128), nullable=True))
    op.add_column('consumables', sa.Column('output_unit', sa.String(32), nullable=True))
    op.add_column('consumables', sa.Column('rate', sa.Numeric(14, 4), nullable=True))
    op.alter_column('consumables', 'name', nullable=True)

    # 2. Update product_process_consumables table
    op.add_column('product_process_consumables', sa.Column('consumable_item', sa.String(128), nullable=True))
    op.add_column('product_process_consumables', sa.Column('part_no_saleable_item', sa.String(128), nullable=True))
    op.add_column('product_process_consumables', sa.Column('used_for_name_of_saleable_part', sa.String(255), nullable=True))
    op.add_column('product_process_consumables', sa.Column('used_part_no_prd_order', sa.String(128), nullable=True))
    op.add_column('product_process_consumables', sa.Column('process_name', sa.String(128), nullable=True))
    op.add_column('product_process_consumables', sa.Column('material_thickness_in_mm_gsm', sa.String(64), nullable=True))
    op.add_column('product_process_consumables', sa.Column('no_of_process_per_part', sa.Numeric(14, 4), server_default='1.0000', nullable=True))
    op.add_column('product_process_consumables', sa.Column('output_unit', sa.String(32), nullable=True))
    op.add_column('product_process_consumables', sa.Column('rate', sa.Numeric(14, 4), nullable=True))

    # 3. Update products table for compound uniqueness on (part_number, item_id)
    # Widen columns to String(128) if needed
    op.alter_column('products', 'part_number', existing_type=sa.String(128), nullable=True)
    op.alter_column('products', 'item_id', existing_type=sa.String(128), nullable=True)
    # Make code nullable or keep default, remove strict unique if code is composite
    try:
        op.drop_index('ix_products_code', table_name='products')
    except Exception:
        pass
    op.create_index('ix_products_code', 'products', ['code'])
    op.create_unique_constraint('uq_products_part_number_item_id', 'products', ['part_number', 'item_id'])


def downgrade() -> None:
    # Downgrade products
    try:
        op.drop_constraint('uq_products_part_number_item_id', 'products', type_='unique')
    except Exception:
        pass

    # Downgrade product_process_consumables
    for col in [
        'consumable_item', 'part_no_saleable_item', 'used_for_name_of_saleable_part',
        'used_part_no_prd_order', 'process_name', 'material_thickness_in_mm_gsm',
        'no_of_process_per_part', 'output_unit', 'rate'
    ]:
        op.drop_column('product_process_consumables', col)

    # Downgrade consumables
    for col in ['supplier_id', 'supplier_name', 'category', 'type_of_material', 'output_unit', 'rate']:
        op.drop_column('consumables', col)
    try:
        op.drop_constraint('uq_consumables_item_id', 'consumables', type_='unique')
        op.drop_constraint('normalized_item_id', 'consumables', type_='check')
    except Exception:
        pass
    op.alter_column('consumables', 'item_id', new_column_name='code', existing_type=sa.String(128), type_=sa.String(64))
