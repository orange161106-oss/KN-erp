"""M2.3 masters, audit foundation, and unassigned permission codes."""
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa

revision = "0005_inventory_masters"
down_revision = "0004_merge_master_heads"
branch_labels = None
depends_on = None


def record_columns():
    return [sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade():
    for table, code_length in (("units", 16), ("suppliers", 64), ("consumables", 64)):
        extra = []
        if table == "consumables":
            extra = [sa.Column("description", sa.Text(), nullable=True),
                     sa.Column("unit_id", sa.Uuid(), nullable=False),
                     sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="RESTRICT", name=op.f("fk_consumables_unit_id_units"))]
        op.create_table(table, *record_columns(),
                        sa.Column("code", sa.String(code_length), nullable=False),
                        sa.Column("name", sa.String(255), nullable=False), *extra,
                        sa.PrimaryKeyConstraint("id", name=op.f("pk_" + table)),
                        sa.UniqueConstraint("code", name=op.f("uq_" + table + "_code")),
                        sa.CheckConstraint("code = upper(btrim(code)) AND length(code) > 0", name=op.f("ck_" + table + "_normalized_code")))
    op.create_index("ix_consumables_unit_id", "consumables", ["unit_id"])
    op.create_table("supplier_consumables", *record_columns(),
                    sa.Column("supplier_id", sa.Uuid(), nullable=False), sa.Column("consumable_id", sa.Uuid(), nullable=False),
                    sa.PrimaryKeyConstraint("id", name=op.f("pk_supplier_consumables")),
                    sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], ondelete="RESTRICT", name=op.f("fk_supplier_consumables_supplier_id_suppliers")),
                    sa.ForeignKeyConstraint(["consumable_id"], ["consumables.id"], ondelete="RESTRICT", name=op.f("fk_supplier_consumables_consumable_id_consumables")),
                    sa.UniqueConstraint("supplier_id", "consumable_id", name=op.f("uq_supplier_consumables_supplier_id")))
    op.create_index("ix_supplier_consumables_supplier_id", "supplier_consumables", ["supplier_id"])
    op.create_index("ix_supplier_consumables_consumable_id", "supplier_consumables", ["consumable_id"])
    op.create_table("audit_logs", sa.Column("id", sa.Uuid(), nullable=False),
                    sa.Column("actor_id", sa.Uuid(), nullable=False), sa.Column("action", sa.String(32), nullable=False),
                    sa.Column("entity_type", sa.String(64), nullable=False), sa.Column("entity_id", sa.Uuid(), nullable=False),
                    sa.Column("old_values", sa.JSON(), nullable=True), sa.Column("new_values", sa.JSON(), nullable=False),
                    sa.Column("reason", sa.Text(), nullable=False),
                    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
                    sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
                    sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_audit_logs_actor_id_users")))
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    permissions = sa.table("permissions", sa.column("id", sa.Uuid()), sa.column("code", sa.String()), sa.column("description", sa.Text()))
    op.bulk_insert(permissions, [
        {"id": uuid5(NAMESPACE_URL, "kn-consumable-erp:permission:" + code), "code": code, "description": action.title() + " " + resource.replace("_", " ") + " master records"}
        for resource in ("units", "consumables", "suppliers", "supplier_consumables")
        for action in ("read", "write")
        for code in ("masters." + resource + "." + action,)
    ])


def downgrade():
    permissions = sa.table("permissions", sa.column("code", sa.String()))
    codes = ["masters." + resource + "." + action for resource in ("units", "consumables", "suppliers", "supplier_consumables") for action in ("read", "write")]
    # Assigned permissions deliberately block downgrade via RESTRICT until reviewed.
    op.execute(permissions.delete().where(permissions.c.code.in_(codes)))
    op.drop_table("audit_logs")
    op.drop_table("supplier_consumables")
    op.drop_table("consumables")
    op.drop_table("suppliers")
    op.drop_table("units")
