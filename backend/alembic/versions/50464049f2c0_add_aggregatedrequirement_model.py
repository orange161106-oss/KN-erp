"""Add AggregatedRequirement model

Revision ID: 50464049f2c0
Revises: 4a7dac394a7d
Create Date: 2026-10-12 12:13:24.875550
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '50464049f2c0'
down_revision: Union[str, Sequence[str], None] = '4a7dac394a7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'aggregated_requirements' not in tables:
        op.create_table(
            'aggregated_requirements',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('month', sa.Integer(), nullable=False),
            sa.Column('year', sa.Integer(), nullable=False),
            sa.Column('consumable_id', sa.Uuid(), nullable=False),
            sa.Column('total_gross_qty', sa.Float(), nullable=False),
            sa.Column('net_purchase_qty', sa.Float(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['consumable_id'], ['consumables.id'], name=op.f('fk_aggregated_requirements_consumable_id_consumables'), ondelete='RESTRICT'),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_aggregated_requirements')),
            sa.UniqueConstraint('month', 'year', 'consumable_id', name='uq_aggregated_requirements_month_year_consumable')
        )
        op.create_index('ix_aggregated_req_consumable', 'aggregated_requirements', ['consumable_id'], unique=False)
        op.create_index('ix_aggregated_req_period', 'aggregated_requirements', ['month', 'year'], unique=False)
        op.create_index(op.f('ix_aggregated_requirements_consumable_id'), 'aggregated_requirements', ['consumable_id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'aggregated_requirements' in tables:
        op.drop_table('aggregated_requirements')
