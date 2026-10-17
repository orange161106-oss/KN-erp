"""merge 8c0f13ab0a53 and c003_purchase_plan_drafts

Revision ID: df4cc3ac8f31
Revises: 8c0f13ab0a53, c003_purchase_plan_drafts
Create Date: 2026-10-17 09:44:33.721034
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'df4cc3ac8f31'
down_revision: Union[str, Sequence[str], None] = ('8c0f13ab0a53', 'c003_purchase_plan_drafts')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
