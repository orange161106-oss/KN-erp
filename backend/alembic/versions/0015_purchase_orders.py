"""M5.3 traced demand and purchase commitments; no stock receipt semantics."""
from uuid import UUID, uuid5

from alembic import op
import sqlalchemy as sa

revision = '0015_purchase_orders'
down_revision = '0014_purchase_approval'
branch_labels = depends_on = None
PERMISSIONS = ('purchase.orders.read', 'purchase.orders.create', 'purchase.orders.issue',
               'purchase.orders.cancel', 'purchase.orders.price', 'purchase.demand.submit')


def fk(name, table, nullable=False):
    return sa.Column(name, sa.Uuid(), sa.ForeignKey(table + '.id', ondelete='RESTRICT'), nullable=nullable)


def upgrade():
    op.create_table('purchase_demand_evidence', sa.Column('id', sa.Uuid(), primary_key=True),
        fk('approval_id', 'purchase_approvals'), sa.Column('submission_key', sa.String(192), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False), sa.Column('report', sa.JSON(), nullable=False),
        fk('submitted_by', 'users'), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('approval_id'), sa.UniqueConstraint('submission_key'))
    op.create_table('purchase_orders', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('po_number', sa.String(64), nullable=False), sa.Column('creation_key', sa.String(192), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False), fk('supplier_id', 'suppliers'),
        sa.Column('supplier_snapshot', sa.JSON(), nullable=False), sa.Column('po_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(16), nullable=False), sa.Column('reason', sa.Text(), nullable=False),
        fk('created_by', 'users'), sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        fk('issued_by', 'users', True), sa.Column('issued_at', sa.DateTime(timezone=True)),
        fk('cancelled_by', 'users', True), sa.Column('cancelled_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('po_number'), sa.UniqueConstraint('creation_key'),
        sa.CheckConstraint("status IN ('DRAFT','ISSUED','CANCELLED')", name='valid_status'))
    op.create_index('ix_purchase_orders_supplier_id', 'purchase_orders', ['supplier_id'])
    op.create_table('purchase_order_items', sa.Column('id', sa.Uuid(), primary_key=True),
        fk('purchase_order_id', 'purchase_orders'), fk('approval_id', 'purchase_approvals'), fk('evidence_id', 'purchase_demand_evidence'),
        fk('consumable_id', 'consumables'), fk('unit_id', 'units'), fk('planning_version_id', 'planning_versions'),
        sa.Column('ordered_quantity', sa.Numeric(18, 4), nullable=False), sa.Column('expected_delivery', sa.DateTime(timezone=True), nullable=False),
        sa.Column('approval_hash', sa.String(64), nullable=False), sa.Column('approval_snapshot', sa.JSON(), nullable=False),
        sa.Column('material_snapshot', sa.JSON(), nullable=False), sa.Column('pricing', sa.JSON()), sa.Column('line_value', sa.Numeric(38, 8)),
        sa.UniqueConstraint('purchase_order_id', 'approval_id'), sa.CheckConstraint('ordered_quantity > 0', name='positive_order_quantity'))
    op.create_index('ix_purchase_order_items_purchase_order_id', 'purchase_order_items', ['purchase_order_id'])
    op.create_index('ix_purchase_order_items_approval_id', 'purchase_order_items', ['approval_id'])
    for table in ('purchase_demand_evidence', 'purchase_order_items'):
        op.execute(f'CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION inventory_append_only()')
    op.execute("""CREATE FUNCTION purchase_order_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'PO history cannot be deleted' USING ERRCODE='55000'; END IF;
      IF OLD.status <> 'DRAFT' OR NEW.status NOT IN ('ISSUED','CANCELLED') OR
         (to_jsonb(NEW) - ARRAY['status','issued_by','issued_at','cancelled_by','cancelled_at']) IS DISTINCT FROM
         (to_jsonb(OLD) - ARRAY['status','issued_by','issued_at','cancelled_by','cancelled_at']) THEN
        RAISE EXCEPTION 'PO terms are immutable; only draft transitions are allowed' USING ERRCODE='55000';
      END IF;
      IF (NEW.status = 'ISSUED' AND (NEW.issued_by IS NULL OR NEW.issued_at IS NULL OR NEW.cancelled_at IS NOT NULL OR NEW.cancelled_by IS NOT NULL)) OR
         (NEW.status = 'CANCELLED' AND (NEW.cancelled_by IS NULL OR NEW.cancelled_at IS NULL OR NEW.issued_at IS NOT NULL OR NEW.issued_by IS NOT NULL)) THEN
        RAISE EXCEPTION 'PO transition requires actor and time' USING ERRCODE='55000';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE TRIGGER purchase_orders_guard BEFORE UPDATE OR DELETE ON purchase_orders FOR EACH ROW EXECUTE FUNCTION purchase_order_guard()')
    permissions = sa.table('permissions', sa.column('id', sa.Uuid()), sa.column('code', sa.String()), sa.column('description', sa.Text()))
    op.bulk_insert(permissions, [{'id': uuid5(UUID('2d98ea56-41e0-40e0-929a-fdf23714891d'), code), 'code': code,
                                  'description': code.replace('.', ' ')} for code in PERMISSIONS])


def downgrade():
    permissions = sa.table('permissions', sa.column('code', sa.String()))
    op.execute(permissions.delete().where(permissions.c.code.in_(PERMISSIONS)))
    op.drop_table('purchase_order_items')
    op.drop_table('purchase_orders')
    op.execute('DROP FUNCTION purchase_order_guard()')
    op.drop_table('purchase_demand_evidence')
