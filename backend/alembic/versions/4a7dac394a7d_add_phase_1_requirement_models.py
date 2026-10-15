"""Add Phase 1 Requirement Models

Revision ID: 4a7dac394a7d
Revises: 5fad54c0a64e
Create Date: 2026-10-12 11:54:58.035018
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '4a7dac394a7d'
down_revision: Union[str, Sequence[str], None] = '5fad54c0a64e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'monthly_requirement_plans' not in tables:
        op.create_table(
            'monthly_requirement_plans',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('plant_id', sa.String(length=64), nullable=False),
            sa.Column('month', sa.Integer(), nullable=False),
            sa.Column('year', sa.Integer(), nullable=False),
            sa.Column('status', sa.Enum('DRAFT', 'SUBMITTED', 'APPROVED', name='requirement_status_enum', native_enum=False), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_monthly_requirement_plans')),
            sa.UniqueConstraint('plant_id', 'month', 'year', name='uq_monthly_requirement_plans_plant_month_year')
        )
        op.create_index('ix_monthly_req_plan_lookup', 'monthly_requirement_plans', ['plant_id', 'month', 'year'], unique=False)
        op.create_index(op.f('ix_monthly_requirement_plans_plant_id'), 'monthly_requirement_plans', ['plant_id'], unique=False)

    if 'requirement_line_items' not in tables:
        op.create_table(
            'requirement_line_items',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('plan_id', sa.Uuid(), nullable=False),
            sa.Column('consumable_id', sa.Uuid(), nullable=False),
            sa.Column('requested_qty', sa.Float(), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['consumable_id'], ['consumables.id'], name=op.f('fk_requirement_line_items_consumable_id_consumables'), ondelete='RESTRICT'),
            sa.ForeignKeyConstraint(['plan_id'], ['monthly_requirement_plans.id'], name=op.f('fk_requirement_line_items_plan_id_monthly_requirement_plans'), ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_requirement_line_items')),
            sa.UniqueConstraint('plan_id', 'consumable_id', name='uq_requirement_line_items_plan_consumable')
        )
        op.create_index('ix_req_line_item_consumable', 'requirement_line_items', ['consumable_id'], unique=False)
        op.create_index('ix_req_line_item_plan', 'requirement_line_items', ['plan_id'], unique=False)
        op.create_index(op.f('ix_requirement_line_items_consumable_id'), 'requirement_line_items', ['consumable_id'], unique=False)
        op.create_index(op.f('ix_requirement_line_items_plan_id'), 'requirement_line_items', ['plan_id'], unique=False)

    if 'users' in tables:
        user_cols = [c['name'] for c in inspector.get_columns('users')]
        if 'assigned_plant' not in user_cols:
            op.add_column('users', sa.Column('assigned_plant', sa.String(length=64), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'requirement_line_items' in tables:
        op.drop_table('requirement_line_items')
    if 'monthly_requirement_plans' in tables:
        op.drop_table('monthly_requirement_plans')

    if 'users' in tables:
        user_cols = [c['name'] for c in inspector.get_columns('users')]
        if 'assigned_plant' in user_cols:
            op.drop_column('users', 'assigned_plant')
