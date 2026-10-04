"""M4.1 append-only replicas of existing ERP stock history and usable snapshots."""
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa

revision = "0011_central_inventory"
down_revision = "0010_requirement_approval"
branch_labels = None
depends_on = None


def pk(table):
    return sa.PrimaryKeyConstraint("id", name=op.f("pk_" + table))


def fk(table, column, target):
    return sa.ForeignKeyConstraint([column], [target + ".id"], ondelete="RESTRICT", name=op.f("fk_" + table + "_" + column + "_" + target))


def upgrade():
    table = "stock_import_batches"
    op.create_table(table,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("export_id", sa.String(192), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_by", sa.Uuid(), nullable=False),
        sa.Column("import_reason", sa.Text(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("movement_count", sa.Integer(), nullable=False),
        sa.Column("snapshot_count", sa.Integer(), nullable=False),
        pk(table), fk(table, "imported_by", "users"),
        sa.UniqueConstraint("export_id", name=op.f("uq_stock_import_batches_export_id")),
    )
    table = "stock_transactions"
    op.create_table(table,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_event_id", sa.String(192), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("consumable_id", sa.Uuid(), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("source_unit_id", sa.Uuid(), nullable=False),
        sa.Column("source_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("conversion_factor", sa.Numeric(24, 12), nullable=False),
        sa.Column("conversion_reference", sa.String(192), nullable=True),
        sa.Column("movement", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("signed_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_actor", sa.String(128), nullable=False),
        pk(table), fk(table, "batch_id", "stock_import_batches"), fk(table, "consumable_id", "consumables"),
        fk(table, "unit_id", "units"), fk(table, "source_unit_id", "units"),
        sa.UniqueConstraint("source_event_id", name=op.f("uq_stock_transactions_source_event_id")),
        sa.CheckConstraint("movement IN ('RECEIPT', 'ISSUE', 'RETURN')", name=op.f("ck_stock_transactions_movement")),
        sa.CheckConstraint("source_quantity > 0 AND quantity > 0 AND conversion_factor > 0", name=op.f("ck_stock_transactions_positive_quantity")),
        sa.CheckConstraint("quantity = source_quantity * conversion_factor", name=op.f("ck_stock_transactions_exact_conversion")),
        sa.CheckConstraint("signed_quantity = CASE WHEN movement = 'ISSUE' THEN -quantity ELSE quantity END", name=op.f("ck_stock_transactions_signed_quantity")),
        sa.CheckConstraint("(source_unit_id = unit_id AND conversion_factor = 1) OR (source_unit_id <> unit_id AND conversion_reference IS NOT NULL AND length(conversion_reference) > 0)", name=op.f("ck_stock_transactions_conversion_reference")),
    )
    op.create_index("ix_stock_transactions_material_time", table, ["consumable_id", "event_at", "id"])
    table = "stock_snapshots"
    op.create_table(table,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_snapshot_id", sa.String(192), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("consumable_id", sa.Uuid(), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("usable_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nonusable_excluded", sa.Boolean(), nullable=False),
        sa.Column("reservations_excluded", sa.Boolean(), nullable=False),
        pk(table), fk(table, "batch_id", "stock_import_batches"), fk(table, "consumable_id", "consumables"), fk(table, "unit_id", "units"),
        sa.UniqueConstraint("source_snapshot_id", name=op.f("uq_stock_snapshots_source_snapshot_id")),
        sa.UniqueConstraint("consumable_id", "as_of", name=op.f("uq_stock_snapshots_consumable_id")),
        sa.CheckConstraint("usable_quantity >= 0", name=op.f("ck_stock_snapshots_nonnegative_quantity")),
        sa.CheckConstraint("nonusable_excluded AND reservations_excluded", name=op.f("ck_stock_snapshots_usable_exclusions")),
    )
    op.execute("""CREATE FUNCTION inventory_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          RAISE EXCEPTION 'Imported stock history is append-only' USING ERRCODE = '55000';
        END $$""")
    for table in ("stock_import_batches", "stock_transactions", "stock_snapshots"):
        op.execute(f"CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION inventory_append_only()")
    permissions = sa.table("permissions", sa.column("id", sa.Uuid()), sa.column("code", sa.String()), sa.column("description", sa.Text()))
    op.bulk_insert(permissions, [
        {"id": uuid5(NAMESPACE_URL, "kn-consumable-erp:permission:" + code), "code": code, "description": description}
        for code, description in (("inventory.stock.read", "Read reported central stock and source history"),
                                  ("inventory.stock.import", "Import normalized existing ERP stock records"))
    ])


def downgrade():
    permissions = sa.table("permissions", sa.column("code", sa.String()))
    op.execute(permissions.delete().where(permissions.c.code.in_(["inventory.stock.read", "inventory.stock.import"])))
    for table in ("stock_snapshots", "stock_transactions", "stock_import_batches"):
        op.drop_table(table)
    op.execute("DROP FUNCTION inventory_append_only()")
