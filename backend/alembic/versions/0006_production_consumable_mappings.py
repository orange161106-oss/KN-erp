"""M2.4 Product-Plant and Product-Process-Consumable Mappings.

Revision ID: 0006_production_consumable_mappings
Revises: 0005_inventory_masters
"""

from alembic import op
import sqlalchemy as sa

revision = "0006_production_consumable_mappings"
down_revision = "0005_inventory_masters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. product_plants
    op.create_table(
        "product_plants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("route_id", sa.Uuid(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT", name=op.f("fk_product_plants_product_id_products")),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="RESTRICT", name=op.f("fk_product_plants_plant_id_plants")),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="RESTRICT", name=op.f("fk_product_plants_route_id_routes")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_plants")),
        sa.UniqueConstraint("product_id", "plant_id", name=op.f("uq_product_plants_product_id_plant_id")),
    )
    op.create_index(op.f("ix_product_plants_product_id"), "product_plants", ["product_id"])
    op.create_index(op.f("ix_product_plants_plant_id"), "product_plants", ["plant_id"])
    op.create_index(op.f("ix_product_plants_route_id"), "product_plants", ["route_id"])

    # 2. product_process_consumables
    op.create_table(
        "product_process_consumables",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("process_id", sa.Uuid(), nullable=False),
        sa.Column("consumable_id", sa.Uuid(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT", name=op.f("fk_product_process_consumables_product_id_products")),
        sa.ForeignKeyConstraint(["process_id"], ["processes.id"], ondelete="RESTRICT", name=op.f("fk_product_process_consumables_process_id_processes")),
        sa.ForeignKeyConstraint(["consumable_id"], ["consumables.id"], ondelete="RESTRICT", name=op.f("fk_product_process_consumables_consumable_id_consumables")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_process_consumables")),
        sa.UniqueConstraint("product_id", "process_id", "consumable_id", name=op.f("uq_product_process_consumables_product_id_process_id_consumable_id")),
    )
    op.create_index(op.f("ix_product_process_consumables_product_id"), "product_process_consumables", ["product_id"])
    op.create_index(op.f("ix_product_process_consumables_process_id"), "product_process_consumables", ["process_id"])
    op.create_index(op.f("ix_product_process_consumables_consumable_id"), "product_process_consumables", ["consumable_id"])


def downgrade() -> None:
    op.drop_table("product_process_consumables")
    op.drop_table("product_plants")
