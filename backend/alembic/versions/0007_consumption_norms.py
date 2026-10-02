"""M3.1 Consumption Rules and Norms.

Revision ID: 0007_consumption_norms
Revises: 0006_production_consumable_mappings
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_consumption_norms"
down_revision = "0006_production_consumable_mappings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consumption_norms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("rule_type", sa.String(32), nullable=False),
        sa.Column("consumable_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("process_id", sa.Uuid(), nullable=True),
        sa.Column("plant_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("rounding_policy", sa.String(32), server_default="NONE", nullable=False),
        sa.Column("rounding_precision", sa.Integer(), server_default="2", nullable=False),
        sa.Column("effective_from", sa.Date(), server_default=sa.func.current_date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["consumable_id"], ["consumables.id"], ondelete="RESTRICT", name=op.f("fk_consumption_norms_consumable_id_consumables")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT", name=op.f("fk_consumption_norms_product_id_products")),
        sa.ForeignKeyConstraint(["process_id"], ["processes.id"], ondelete="RESTRICT", name=op.f("fk_consumption_norms_process_id_processes")),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="RESTRICT", name=op.f("fk_consumption_norms_plant_id_plants")),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="RESTRICT", name=op.f("fk_consumption_norms_unit_id_units")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consumption_norms")),
    )
    op.create_index(op.f("ix_consumption_norms_consumable_id"), "consumption_norms", ["consumable_id"])
    op.create_index(op.f("ix_consumption_norms_product_id"), "consumption_norms", ["product_id"])
    op.create_index(op.f("ix_consumption_norms_process_id"), "consumption_norms", ["process_id"])
    op.create_index(op.f("ix_consumption_norms_plant_id"), "consumption_norms", ["plant_id"])
    op.create_index(
        "ix_consumption_norms_lookup",
        "consumption_norms",
        ["consumable_id", "product_id", "process_id", "plant_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_table("consumption_norms")
