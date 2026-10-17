"""Add output_per_unit, rule_type, and purchasing_unit to consumables and consumption_norms.

Revision ID: c004_tool_life_and_output_per_unit
Revises: c003_purchase_plan_drafts
"""
from alembic import op
import sqlalchemy as sa

revision = 'c004_tool_life_and_output_per_unit'
down_revision = 'c003_purchase_plan_drafts'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE consumables ADD COLUMN IF NOT EXISTS output_per_unit NUMERIC(14, 4);"))
    conn.execute(sa.text("ALTER TABLE consumables ADD COLUMN IF NOT EXISTS rule_type VARCHAR(32) DEFAULT 'TOOL_LIFE';"))
    conn.execute(sa.text("ALTER TABLE consumables ADD COLUMN IF NOT EXISTS purchasing_unit VARCHAR(32);"))
    conn.execute(sa.text("ALTER TABLE consumption_norms ADD COLUMN IF NOT EXISTS output_per_unit NUMERIC(14, 4);"))


def downgrade():
    conn = op.get_bind()
    conn.execute(sa.text("ALTER TABLE consumption_norms DROP COLUMN IF EXISTS output_per_unit;"))
    conn.execute(sa.text("ALTER TABLE consumables DROP COLUMN IF EXISTS purchasing_unit;"))
    conn.execute(sa.text("ALTER TABLE consumables DROP COLUMN IF EXISTS rule_type;"))
    conn.execute(sa.text("ALTER TABLE consumables DROP COLUMN IF EXISTS output_per_unit;"))

