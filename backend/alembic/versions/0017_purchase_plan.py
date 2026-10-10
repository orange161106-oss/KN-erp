"""0017_purchase_plan - Monthly Purchase Planning table structure."""

from alembic import op
import sqlalchemy as sa

revision = "0017_purchase_plan"
down_revision = "0016_grn_imports"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "purchase_plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("planning_period", sa.String(7), nullable=False),
        sa.Column("planning_version_id", sa.Uuid(), sa.ForeignKey("planning_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("revision_label", sa.String(16), nullable=False, server_default="R1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("msl_days_gas", sa.Numeric(10, 2), nullable=False, server_default="2.0"),
        sa.Column("msl_days_general", sa.Numeric(10, 2), nullable=False, server_default="10.0"),
        sa.Column("month_days", sa.Integer(), nullable=False, server_default="31"),
        sa.Column("working_days", sa.Integer(), nullable=False, server_default="27"),
        sa.Column("source_filename", sa.String(255), nullable=True),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("modified_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("modified_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint("planning_period", name="uq_purchase_plan_period"),
    )
    op.create_index("ix_purchase_plan_period", "purchase_plans", ["planning_period"])

    op.create_table(
        "purchase_plan_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey("purchase_plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("s_no", sa.Integer(), nullable=True),
        sa.Column("item_id", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("req_type", sa.String(64), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("type_of_material", sa.String(64), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False, server_default="PCS"),
        sa.Column("purchasing_unit", sa.String(32), nullable=True),
        sa.Column("output_per_unit", sa.Numeric(14, 4), nullable=True),
        sa.Column("rate", sa.Numeric(14, 4), nullable=True),
        sa.Column("moq", sa.Numeric(14, 4), nullable=True),
        sa.Column("min_stock_level", sa.Numeric(14, 4), nullable=True),
        sa.Column("max_stock_level", sa.Numeric(14, 4), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("prev_opening_qty", sa.Numeric(14, 4), nullable=True),
        sa.Column("prev_opening_val", sa.Numeric(14, 4), nullable=True),
        sa.Column("prev_receipt_qty", sa.Numeric(14, 4), nullable=True),
        sa.Column("prev_issue_qty", sa.Numeric(14, 4), nullable=True),
        sa.Column("prev_closing_qty", sa.Numeric(14, 4), nullable=True),
        sa.Column("prev_closing_val", sa.Numeric(14, 4), nullable=True),
        sa.Column("prev_prd_qty", sa.Numeric(14, 4), nullable=True),
        sa.Column("sch_qty", sa.Numeric(14, 4), nullable=True),
        sa.Column("req_qty", sa.Numeric(14, 4), nullable=True),
        sa.Column("order_qty", sa.Numeric(14, 4), nullable=True),
        sa.Column("order_value", sa.Numeric(14, 4), nullable=True),
        sa.Column("receipt_qty", sa.Numeric(14, 4), nullable=True),
        sa.Column("receipt_value", sa.Numeric(14, 4), nullable=True),
        sa.Column("sch_qty_r2", sa.Numeric(14, 4), nullable=True),
        sa.Column("req_qty_r2", sa.Numeric(14, 4), nullable=True),
        sa.Column("order_qty_r2", sa.Numeric(14, 4), nullable=True),
        sa.Column("order_value_r2", sa.Numeric(14, 4), nullable=True),
        sa.Column("receipt_qty_r2", sa.Numeric(14, 4), nullable=True),
        sa.Column("receipt_val_r2", sa.Numeric(14, 4), nullable=True),
        sa.Column("pur_qty", sa.Numeric(14, 4), nullable=True),
        sa.Column("pur_value", sa.Numeric(14, 4), nullable=True),
        sa.Column("bal_pur_qty", sa.Numeric(14, 4), nullable=True),
        sa.Column("bal_pur_value", sa.Numeric(14, 4), nullable=True),
        sa.Column("supplier_id", sa.String(64), nullable=True),
        sa.Column("supplier_name", sa.String(255), nullable=True),
        sa.Column("part_no_saleable", sa.String(64), nullable=True),
        sa.Column("saleable_part_name", sa.String(255), nullable=True),
        sa.Column("used_part_no", sa.String(64), nullable=True),
        sa.Column("process_name", sa.String(128), nullable=True),
        sa.Column("thickness_gsm", sa.String(64), nullable=True),
        sa.Column("no_of_process_per_part", sa.Numeric(10, 2), nullable=True),
        sa.Column("plant_allocations", sa.JSON(), nullable=True),
        sa.Column("consumption_analysis", sa.JSON(), nullable=True),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("is_modified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_purchase_plan_item_plan", "purchase_plan_items", ["plan_id"])
    op.create_index("ix_purchase_plan_item_code", "purchase_plan_items", ["item_id"])


def downgrade():
    op.drop_table("purchase_plan_items")
    op.drop_table("purchase_plans")
