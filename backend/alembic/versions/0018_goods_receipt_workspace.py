"""Goods receipts Excel-style workspace table and CRUD permissions."""
from uuid import UUID, uuid5

from alembic import op
import sqlalchemy as sa

revision = '0018_goods_receipt_workspace'
down_revision = '0017_report_permissions'
branch_labels = depends_on = None

PERMISSIONS = (
    ('purchase.grns.create', 'Create goods receipt records in Excel workspace'),
    ('purchase.grns.update', 'Update goods receipt records in Excel workspace'),
    ('purchase.grns.delete', 'Delete goods receipt records in Excel workspace'),
    ('purchase.grns.export', 'Export goods receipt records to Excel workbook'),
)


def upgrade():
    op.create_table(
        'goods_receipt_records',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('row_index', sa.Integer(), nullable=True),
        sa.Column('part_number', sa.String(128), nullable=False),
        sa.Column('item_id', sa.String(128), nullable=False),
        sa.Column('description', sa.String(256), nullable=False),
        sa.Column('quantity', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('unit', sa.String(64), nullable=False, server_default='Nos'),
        sa.Column('po_number', sa.String(128), nullable=True),
        sa.Column('supplier_name', sa.String(256), nullable=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='SAVED'),
        sa.Column('source_grn_id', sa.String(192), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_by', sa.Uuid(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_goods_receipt_records_part_number', 'goods_receipt_records', ['part_number'])
    op.create_index('ix_goods_receipt_records_is_deleted', 'goods_receipt_records', ['is_deleted'])

    permissions = sa.table('permissions', sa.column('id', sa.Uuid()), sa.column('code', sa.String()), sa.column('description', sa.Text()))
    op.bulk_insert(permissions, [
        {
            'id': uuid5(UUID('2d98ea56-41e0-40e0-929a-fdf23714891d'), code),
            'code': code,
            'description': description,
        }
        for code, description in PERMISSIONS
    ])


def downgrade():
    op.drop_table('goods_receipt_records')
    permissions = sa.table('permissions', sa.column('code', sa.String()))
    op.execute(permissions.delete().where(permissions.c.code.in_([code for code, _ in PERMISSIONS])))

