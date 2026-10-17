"""merge_c004_and_df4cc3ac8f31

Revision ID: 190996207995
Revises: c004_tool_life_and_output_per_unit, df4cc3ac8f31
Create Date: 2026-10-17 15:07:35.525210
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '190996207995'
down_revision: Union[str, Sequence[str], None] = ('c004_tool_life_and_output_per_unit', 'df4cc3ac8f31')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
