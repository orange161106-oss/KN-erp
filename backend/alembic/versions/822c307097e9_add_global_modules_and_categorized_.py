"""add global modules and categorized alert flags

Revision ID: 822c307097e9
Revises: 98f094700977
Create Date: 2026-10-09 10:53:19.046339
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '822c307097e9'
down_revision: Union[str, Sequence[str], None] = '98f094700977'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('can_access_dashboard', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('users', sa.Column('can_access_reports', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('users', sa.Column('alert_production', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('users', sa.Column('alert_inventory', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('users', sa.Column('alert_purchasing', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('users', sa.Column('alert_system', sa.Boolean(), server_default=sa.text('false'), nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'alert_system')
    op.drop_column('users', 'alert_purchasing')
    op.drop_column('users', 'alert_inventory')
    op.drop_column('users', 'alert_production')
    op.drop_column('users', 'can_access_reports')
    op.drop_column('users', 'can_access_dashboard')
