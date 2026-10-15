"""merge_audit_and_requirement_workspace_heads

Revision ID: 5fad54c0a64e
Revises: 0022_monthly_requirement_workspace, 64d7acf6b486
Create Date: 2026-10-12 10:11:37.126301
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5fad54c0a64e'
down_revision: Union[str, Sequence[str], None] = ('0022_monthly_requirement_workspace', '64d7acf6b486')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
