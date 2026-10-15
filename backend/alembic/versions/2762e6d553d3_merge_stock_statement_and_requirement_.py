"""merge stock statement and requirement heads

Revision ID: 2762e6d553d3
Revises: 0027_stock_statement_store_group_and_consumable_source, 6a8f91eb9f30
Create Date: 2026-10-15 13:03:49.260829
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2762e6d553d3'
down_revision: Union[str, Sequence[str], None] = ('0027_stock_statement_store_group_and_consumable_source', '6a8f91eb9f30')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
