"""Add serial_no and part_no to requirement_line_items and merge heads

Revision ID: 6a8f91eb9f30
Revises: ('50464049f2c0', '0025_add_item_class_to_stock_statement_lines')
Create Date: 2026-10-13 09:44:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6a8f91eb9f30'
down_revision: Union[str, Sequence[str], None] = ('50464049f2c0', '0025_add_item_class_to_stock_statement_lines')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'requirement_line_items' in tables:
        columns = [c['name'] for c in inspector.get_columns('requirement_line_items')]
        if 'serial_no' not in columns:
            op.add_column('requirement_line_items', sa.Column('serial_no', sa.Integer(), nullable=True))
        if 'part_no' not in columns:
            op.add_column('requirement_line_items', sa.Column('part_no', sa.String(length=128), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'requirement_line_items' in tables:
        columns = [c['name'] for c in inspector.get_columns('requirement_line_items')]
        if 'part_no' in columns:
            op.drop_column('requirement_line_items', 'part_no')
        if 'serial_no' in columns:
            op.drop_column('requirement_line_items', 'serial_no')
