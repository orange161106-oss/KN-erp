"""Keep requested purchase quantities separate from calculated/approved evidence."""
from alembic import op
import sqlalchemy as sa

revision = 'c003_purchase_plan_drafts'
down_revision = 'c002_optional_catalog_stock_units'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table('purchase_plan_drafts'):
        op.create_table('purchase_plan_drafts',
            sa.Column('id', sa.Uuid(), primary_key=True),
            sa.Column('planning_version_id', sa.Uuid(), sa.ForeignKey('planning_versions.id', ondelete='RESTRICT'), nullable=False),
            sa.Column('consumable_id', sa.Uuid(), sa.ForeignKey('consumables.id', ondelete='RESTRICT'), nullable=False),
            sa.Column('unit_id', sa.Uuid(), sa.ForeignKey('units.id', ondelete='RESTRICT'), nullable=False),
            sa.Column('requested_qty', sa.Numeric(18, 4), nullable=True),
            sa.Column('notes', sa.Text(), nullable=True),
            sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
            sa.Column('updated_by', sa.Uuid(), sa.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint('planning_version_id', 'consumable_id', name='uq_purchase_plan_draft_version_material'),
            sa.CheckConstraint('requested_qty IS NULL OR requested_qty >= 0', name='nonnegative_requested_qty'),
        )


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM purchase_plan_drafts)')):
        raise RuntimeError('Purchase drafts contain review history; archive it before downgrading.')
    op.drop_table('purchase_plan_drafts')
