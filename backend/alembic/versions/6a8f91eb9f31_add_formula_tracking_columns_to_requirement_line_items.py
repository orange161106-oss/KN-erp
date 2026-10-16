"""add formula tracking columns to requirement_line_items

Revision ID: 6a8f91eb9f31
Revises: 2762e6d553d3
Create Date: 2026-10-16 11:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6a8f91eb9f31'
down_revision: Union[str, Sequence[str], None] = '2762e6d553d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'requirement_line_items',
        sa.Column('formula_qty', sa.Float(), nullable=False, server_default='0.0')
    )
    op.add_column(
        'requirement_line_items',
        sa.Column('approved_qty', sa.Float(), nullable=False, server_default='0.0')
    )
    op.add_column(
        'requirement_line_items',
        sa.Column('is_modified', sa.Boolean(), nullable=False, server_default='false')
    )
    op.add_column(
        'requirement_line_items',
        sa.Column('modification_reason', sa.String(length=512), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('requirement_line_items', 'modification_reason')
    op.drop_column('requirement_line_items', 'is_modified')
    op.drop_column('requirement_line_items', 'approved_qty')
    op.drop_column('requirement_line_items', 'formula_qty')
