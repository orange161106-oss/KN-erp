"""remove_can_access_reports

Revision ID: cd63eeb15edc
Revises: 822c307097e9
Create Date: 2026-10-09 16:12:51.224886
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'cd63eeb15edc'
down_revision: Union[str, Sequence[str], None] = '822c307097e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('users', 'can_access_reports')


def downgrade() -> None:
    op.add_column('users', sa.Column('can_access_reports', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False))
