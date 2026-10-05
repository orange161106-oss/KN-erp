"""M3.3 Requirement Calculation Orchestrator.

Revision ID: 0008_calculated_requirements
Revises: 0007_consumption_norms
"""

from alembic import op
import sqlalchemy as sa

revision = "0008_calculated_requirements"
down_revision = "0007_consumption_norms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calculated_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("planning_version_id", sa.Uuid(), nullable=False),
        sa.Column("prd_order_item_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=False),
        sa.Column("process_id", sa.Uuid(), nullable=False),
        sa.Column("consumable_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.Uuid(), nullable=False),
        sa.Column("rule_type", sa.String(32), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("source_production_qty", sa.Numeric(14, 4), nullable=False),
        sa.Column("raw_requirement", sa.Numeric(14, 4), nullable=False),
        sa.Column("rounding_policy", sa.String(32), nullable=False),
        sa.Column("rounding_precision", sa.Integer(), nullable=False),
        sa.Column("calculated_qty", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit_id", sa.Uuid(), nullable=False),
        sa.Column("uom", sa.String(16), nullable=False),
        sa.Column("calculation_steps", sa.JSON(), nullable=False),
        sa.Column("explanation_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["planning_version_id"], ["planning_versions.id"], ondelete="CASCADE", name=op.f("fk_calculated_requirements_planning_version_id_planning_versions")),
        sa.ForeignKeyConstraint(["prd_order_item_id"], ["prd_order_items.id"], ondelete="CASCADE", name=op.f("fk_calculated_requirements_prd_order_item_id_prd_order_items")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT", name=op.f("fk_calculated_requirements_product_id_products")),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="RESTRICT", name=op.f("fk_calculated_requirements_plant_id_plants")),
        sa.ForeignKeyConstraint(["process_id"], ["processes.id"], ondelete="RESTRICT", name=op.f("fk_calculated_requirements_process_id_processes")),
        sa.ForeignKeyConstraint(["consumable_id"], ["consumables.id"], ondelete="RESTRICT", name=op.f("fk_calculated_requirements_consumable_id_consumables")),
        sa.ForeignKeyConstraint(["rule_id"], ["consumption_norms.id"], ondelete="RESTRICT", name=op.f("fk_calculated_requirements_rule_id_consumption_norms")),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], ondelete="RESTRICT", name=op.f("fk_calculated_requirements_unit_id_units")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calculated_requirements")),
        sa.UniqueConstraint("prd_order_item_id", "process_id", "consumable_id", name="uq_calculated_req_item_process_consumable"),
    )
    op.create_index("ix_calc_req_version", "calculated_requirements", ["planning_version_id"])
    op.create_index("ix_calc_req_version_plant", "calculated_requirements", ["planning_version_id", "plant_id"])
    op.create_index("ix_calc_req_version_consumable", "calculated_requirements", ["planning_version_id", "consumable_id"])

    op.create_table(
        "requirement_calculation_errors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("planning_version_id", sa.Uuid(), nullable=False),
        sa.Column("prd_order_item_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("plant_id", sa.Uuid(), nullable=True),
        sa.Column("consumable_id", sa.Uuid(), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("context_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["planning_version_id"], ["planning_versions.id"], ondelete="CASCADE", name=op.f("fk_requirement_calculation_errors_planning_version_id_planning_versions")),
        sa.ForeignKeyConstraint(["prd_order_item_id"], ["prd_order_items.id"], ondelete="CASCADE", name=op.f("fk_requirement_calculation_errors_prd_order_item_id_prd_order_items")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT", name=op.f("fk_requirement_calculation_errors_product_id_products")),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="SET NULL", name=op.f("fk_requirement_calculation_errors_plant_id_plants")),
        sa.ForeignKeyConstraint(["consumable_id"], ["consumables.id"], ondelete="SET NULL", name=op.f("fk_requirement_calculation_errors_consumable_id_consumables")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_requirement_calculation_errors")),
    )
    op.create_index("ix_calc_err_version", "requirement_calculation_errors", ["planning_version_id"])


def downgrade() -> None:
    op.drop_table("requirement_calculation_errors")
    op.drop_table("calculated_requirements")

