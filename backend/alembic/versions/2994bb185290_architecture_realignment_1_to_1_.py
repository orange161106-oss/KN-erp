"""Add workflow visibility flags without removing existing operation grants.

Revision ID: 2994bb185290
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa

revision = "2994bb185290"
down_revision = "0021"
branch_labels = None
depends_on = None

WORKFLOW_FLAGS = ('can_access_masters', 'can_access_production_mappings', 'can_access_consumption_norms', 'can_access_prd_planning', 'can_access_requirements', 'can_access_plant_workflow', 'can_access_inventory', 'can_access_purchase', 'can_access_purchase_orders', 'can_access_goods_receipts')


def upgrade():
    for name in WORKFLOW_FLAGS:
        op.add_column("users", sa.Column(name, sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    for name in reversed(WORKFLOW_FLAGS):
        op.drop_column("users", name)
