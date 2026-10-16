"""Central basic requirements and explicit zero production rows.

Revision ID: c001_central_basic_planning
Revises: 2762e6d553d3, e002_master_period_uploads
"""
from alembic import op
import sqlalchemy as sa

revision = 'c001_central_basic_planning'
down_revision = ('2762e6d553d3', 'e002_master_period_uploads')
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('calculated_requirements', 'plant_id', existing_type=sa.Uuid(), nullable=True)
    op.drop_constraint(op.f('ck_prd_order_items_planned_quantity_positive'), 'prd_order_items', type_='check')
    op.create_check_constraint(op.f('ck_prd_order_items_planned_quantity_positive'), 'prd_order_items', 'planned_quantity >= 0')


def downgrade():
    connection = op.get_bind()
    if connection.scalar(sa.text('SELECT COUNT(*) FROM calculated_requirements WHERE plant_id IS NULL')):
        raise RuntimeError('Central requirements exist. Downgrade would require inventing plant assignments; no data was removed.')
    if connection.scalar(sa.text('SELECT COUNT(*) FROM prd_order_items WHERE planned_quantity = 0')):
        raise RuntimeError('Zero production rows exist. Preserve revision history before downgrading; no data was removed.')
    op.drop_constraint(op.f('ck_prd_order_items_planned_quantity_positive'), 'prd_order_items', type_='check')
    op.create_check_constraint(op.f('ck_prd_order_items_planned_quantity_positive'), 'prd_order_items', 'planned_quantity > 0')
    op.alter_column('calculated_requirements', 'plant_id', existing_type=sa.Uuid(), nullable=False)
