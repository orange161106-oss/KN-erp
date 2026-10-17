"""PRD planning Excel workspace table and permissions.

Revision ID: 0019_prd_workspace
Revises: 0018_goods_receipt_workspace
"""
from uuid import UUID, uuid5
from alembic import op
import sqlalchemy as sa

revision = '0019_prd_workspace'
down_revision = '0018_goods_receipt_workspace'
branch_labels = depends_on = None

PERMISSIONS = (
    ('prd.records.read', 'Read PRD planning records'),
    ('prd.records.create', 'Create PRD planning records in Excel workspace'),
    ('prd.records.update', 'Update PRD planning records in Excel workspace'),
    ('prd.records.delete', 'Delete PRD planning records in Excel workspace'),
    ('prd.records.export', 'Export PRD planning records to Excel'),
    ('prd.records.import', 'Import PRD planning records from Excel'),
)


def upgrade():
    op.create_table(
        'prd_records',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('row_index', sa.Integer(), nullable=True),
        sa.Column('plant', sa.String(64), nullable=False),
        sa.Column('customer', sa.String(128), nullable=True),
        sa.Column('product_code', sa.String(128), nullable=False),
        sa.Column('description', sa.String(256), nullable=False),
        sa.Column('planned_quantity', sa.Numeric(14, 4), nullable=False, server_default='0'),
        sa.Column('uom', sa.String(32), nullable=False, server_default='Nos'),
        sa.Column('target_period', sa.String(32), nullable=False),
        sa.Column('planning_version', sa.String(32), nullable=False, server_default='V1'),
        sa.Column('status', sa.String(32), nullable=False, server_default='SAVED'),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_by', sa.Uuid(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        if_not_exists=True,
    )

    permissions = sa.table('permissions', sa.column('id', sa.Uuid()), sa.column('code', sa.String()), sa.column('description', sa.Text()))
    for code, description in PERMISSIONS:
        op.execute(
            sa.text(
                "INSERT INTO permissions (id, code, description) "
                "VALUES (:id, :code, :description) "
                "ON CONFLICT (code) DO NOTHING"
            ).bindparams(
                id=uuid5(UUID('2d98ea56-41e0-40e0-929a-fdf23714891d'), code),
                code=code,
                description=description,
            )
        )


def downgrade():
    op.drop_table('prd_records')

