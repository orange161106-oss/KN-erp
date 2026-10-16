"""Allow saved consumable catalogs to await a reviewed stock unit.

Revision ID: c002_optional_catalog_stock_units
Revises: c001_central_basic_planning
"""
from alembic import op
import sqlalchemy as sa

revision = 'c002_optional_catalog_stock_units'
down_revision = 'c001_central_basic_planning'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('consumables', 'unit_id', existing_type=sa.Uuid(), nullable=True)


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT COUNT(*) FROM consumables WHERE unit_id IS NULL')):
        raise RuntimeError('Consumables await stock units. Assign reviewed units before downgrade; no records were removed.')
    op.alter_column('consumables', 'unit_id', existing_type=sa.Uuid(), nullable=False)
