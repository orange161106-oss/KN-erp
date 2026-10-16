"""add mrp grn overwrite columns

Revision ID: 8c0f13ab0a53
Revises: 7b9e02fc0a42
Create Date: 2026-10-16 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '8c0f13ab0a53'
down_revision: Union[str, Sequence[str], None] = '7b9e02fc0a42'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    mrp_cols = {c['name'] for c in insp.get_columns('monthly_requirement_records')}
    for col_name, sa_col in [
        ('plant_id', sa.Column('plant_id', sa.String(64), nullable=True)),
        ('opening_stock', sa.Column('opening_stock', sa.Numeric(14, 4), server_default='0.0', nullable=False)),
        ('grn_received_qty', sa.Column('grn_received_qty', sa.Numeric(14, 4), server_default='0.0', nullable=False)),
        ('consumed_qty', sa.Column('consumed_qty', sa.Numeric(14, 4), server_default='0.0', nullable=False)),
        ('closing_stock', sa.Column('closing_stock', sa.Numeric(14, 4), server_default='0.0', nullable=False)),
        ('gross_requirement', sa.Column('gross_requirement', sa.Numeric(14, 4), server_default='0.0', nullable=False)),
        ('net_order_requirement', sa.Column('net_order_requirement', sa.Numeric(14, 4), server_default='0.0', nullable=False)),
        ('last_synced_at', sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True)),
        ('grn_source_file', sa.Column('grn_source_file', sa.String(255), nullable=True)),
        ('invoice_no', sa.Column('invoice_no', sa.String(128), nullable=True)),
        ('grn_date', sa.Column('grn_date', sa.DateTime(timezone=True), nullable=True)),
    ]:
        if col_name not in mrp_cols:
            op.add_column('monthly_requirement_records', sa_col)

    indexes = {idx['name'] for idx in insp.get_indexes('monthly_requirement_records')}
    if 'ix_monthly_req_plant_period' not in indexes:
        op.create_index('ix_monthly_req_plant_period', 'monthly_requirement_records', ['plant_id', 'planning_month', 'planning_year'])


def downgrade() -> None:
    op.drop_index('ix_monthly_req_plant_period', table_name='monthly_requirement_records')
    op.drop_column('monthly_requirement_records', 'grn_date')
    op.drop_column('monthly_requirement_records', 'invoice_no')
    op.drop_column('monthly_requirement_records', 'grn_source_file')
    op.drop_column('monthly_requirement_records', 'last_synced_at')
    op.drop_column('monthly_requirement_records', 'net_order_requirement')
    op.drop_column('monthly_requirement_records', 'gross_requirement')
    op.drop_column('monthly_requirement_records', 'closing_stock')
    op.drop_column('monthly_requirement_records', 'consumed_qty')
    op.drop_column('monthly_requirement_records', 'grn_received_qty')
    op.drop_column('monthly_requirement_records', 'opening_stock')
    op.drop_column('monthly_requirement_records', 'plant_id')
