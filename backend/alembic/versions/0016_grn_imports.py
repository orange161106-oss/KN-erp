"""M5.4 immutable ERP GRNs linked to PO fulfilment and source stock."""
from uuid import UUID, uuid5

from alembic import op
import sqlalchemy as sa

revision = '0016_grn_imports'
down_revision = '0015_purchase_orders'
branch_labels = depends_on = None
PERMISSIONS = ('purchase.grns.read', 'purchase.grns.import')


def fk(name, table, nullable=False):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey(table + '.id', ondelete='RESTRICT'), nullable=nullable)


def upgrade():
    op.create_table('grns', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('source_grn_id', sa.String(192), nullable=False), sa.Column('payload_hash', sa.String(64), nullable=False),
        fk('purchase_order_id', 'purchase_orders'), fk('supplier_id', 'suppliers'), fk('stock_batch_id', 'stock_import_batches'),
        sa.Column('event_at', sa.DateTime(timezone=True), nullable=False), sa.Column('source_actor', sa.String(128), nullable=False),
        fk('imported_by', 'users'), sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False), sa.UniqueConstraint('source_grn_id'))
    op.create_index('ix_grns_purchase_order_id', 'grns', ['purchase_order_id'])
    op.create_table('grn_items', sa.Column('id', sa.Uuid(), primary_key=True), fk('grn_id', 'grns'),
        sa.Column('source_line_id', sa.String(192), nullable=False), fk('purchase_order_item_id', 'purchase_order_items'),
        fk('consumable_id', 'consumables'), fk('unit_id', 'units'),
        sa.Column('received_quantity', sa.Numeric(18, 4), nullable=False),
        sa.Column('accepted_quantity', sa.Numeric(18, 4), nullable=False),
        sa.Column('rejected_quantity', sa.Numeric(18, 4), nullable=False),
        fk('stock_transaction_id', 'stock_transactions', True), fk('stock_snapshot_id', 'stock_snapshots'),
        sa.UniqueConstraint('grn_id', 'source_line_id'), sa.UniqueConstraint('grn_id', 'purchase_order_item_id', name='uq_grn_items_grn_id_po_item'),
        sa.UniqueConstraint('stock_transaction_id'),
        sa.CheckConstraint('received_quantity > 0 AND accepted_quantity >= 0 AND rejected_quantity >= 0', name='valid_quantities'),
        sa.CheckConstraint('received_quantity = accepted_quantity + rejected_quantity', name='quantity_split'),
        sa.CheckConstraint('(accepted_quantity = 0 AND stock_transaction_id IS NULL) OR (accepted_quantity > 0 AND stock_transaction_id IS NOT NULL)', name='accepted_stock_link'))
    op.create_index('ix_grn_items_grn_id', 'grn_items', ['grn_id'])
    op.create_index('ix_grn_items_purchase_order_item_id', 'grn_items', ['purchase_order_item_id'])
    for table in ('grns', 'grn_items'):
        op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION inventory_append_only()')
    permissions = sa.table('permissions', sa.column('id', sa.Uuid()), sa.column('code', sa.String()), sa.column('description', sa.Text()))
    op.bulk_insert(permissions, [{'id': uuid5(UUID('2d98ea56-41e0-40e0-929a-fdf23714891d'), code), 'code': code,
                                 'description': code.replace('.', ' ')} for code in PERMISSIONS])


def downgrade():
    op.drop_table('grn_items')
    op.drop_table('grns')
    permissions = sa.table('permissions', sa.column('code', sa.String()))
    op.execute(permissions.delete().where(permissions.c.code.in_(PERMISSIONS)))
