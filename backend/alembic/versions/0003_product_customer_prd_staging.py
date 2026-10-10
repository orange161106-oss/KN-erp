"""Product, Customer and PRD import staging.

Revision ID: 0003_product_customer_prd_staging
Revises: 0002_auth_rbac
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_product_customer_prd_staging"
down_revision = "0002_auth_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. products
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("uom", sa.String(16), server_default="PCS", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_products")),
        sa.UniqueConstraint("code", name=op.f("uq_products_code")),
    )
    op.create_index(op.f("ix_products_code"), "products", ["code"])

    # 2. customers
    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
        sa.UniqueConstraint("code", name=op.f("uq_customers_code")),
    )
    op.create_index(op.f("ix_customers_code"), "customers", ["code"])

    # 3. planning_versions
    op.create_table(
        "planning_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("planning_period", sa.String(7), nullable=False),
        sa.Column("version_number", sa.Integer(), server_default="0", nullable=False),
        sa.Column("revision_label", sa.String(16), server_default="R0", nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_filename", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), server_default="DRAFT", nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_planning_versions_created_by_users")),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_planning_versions_approved_by_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_planning_versions")),
        sa.UniqueConstraint("planning_period", "version_number", name=op.f("uq_planning_period_version")),
    )
    op.create_index(op.f("ix_planning_versions_planning_period"), "planning_versions", ["planning_period"])

    # 4. import_batches
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("planning_version_id", sa.Uuid(), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("valid_row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(32), server_default="STAGING", nullable=False),
        sa.Column("staged_data", sa.JSON(), nullable=True),
        sa.Column("uploaded_by", sa.Uuid(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["planning_version_id"], ["planning_versions.id"], ondelete="SET NULL", name=op.f("fk_import_batches_planning_version_id_planning_versions")),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_import_batches_uploaded_by_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_batches")),
    )
    op.create_index(op.f("ix_import_batches_status"), "import_batches", ["status"])

    # 5. import_errors
    op.create_table(
        "import_errors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("column_name", sa.String(64), nullable=True),
        sa.Column("error_code", sa.String(64), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("raw_value", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"], ondelete="CASCADE", name=op.f("fk_import_errors_import_batch_id_import_batches")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_import_errors")),
    )
    op.create_index(op.f("ix_import_errors_import_batch_id"), "import_errors", ["import_batch_id"])

    # 6. prd_order_headers
    op.create_table(
        "prd_order_headers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("planning_version_id", sa.Uuid(), nullable=False),
        sa.Column("import_batch_id", sa.Uuid(), nullable=False),
        sa.Column("planning_period", sa.String(7), nullable=False),
        sa.Column("total_planned_qty", sa.Numeric(14, 4), server_default="0", nullable=False),
        sa.Column("total_line_items", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["planning_version_id"], ["planning_versions.id"], ondelete="CASCADE", name=op.f("fk_prd_order_headers_planning_version_id_planning_versions")),
        sa.ForeignKeyConstraint(["import_batch_id"], ["import_batches.id"], ondelete="RESTRICT", name=op.f("fk_prd_order_headers_import_batch_id_import_batches")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prd_order_headers")),
    )

    # 7. prd_order_items
    op.create_table(
        "prd_order_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("planning_version_id", sa.Uuid(), nullable=False),
        sa.Column("header_id", sa.Uuid(), nullable=False),
        sa.Column("source_row_number", sa.Integer(), nullable=False),
        sa.Column("product_code", sa.String(64), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("plant_code", sa.String(32), nullable=False),
        sa.Column("planned_quantity", sa.Numeric(14, 4), nullable=False),
        sa.Column("uom", sa.String(16), server_default="PCS", nullable=False),
        sa.Column("target_period", sa.String(7), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("planned_quantity > 0", name=op.f("ck_prd_order_items_planned_quantity_positive")),
        sa.ForeignKeyConstraint(["planning_version_id"], ["planning_versions.id"], ondelete="CASCADE", name=op.f("fk_prd_order_items_planning_version_id_planning_versions")),
        sa.ForeignKeyConstraint(["header_id"], ["prd_order_headers.id"], ondelete="CASCADE", name=op.f("fk_prd_order_items_header_id_prd_order_headers")),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="RESTRICT", name=op.f("fk_prd_order_items_product_id_products")),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="SET NULL", name=op.f("fk_prd_order_items_customer_id_customers")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prd_order_items")),
        sa.UniqueConstraint("planning_version_id", "product_id", "plant_code", "target_period", name=op.f("uq_prd_item_version_product_plant_period")),
    )
    op.create_index(op.f("ix_prd_order_items_planning_version_id"), "prd_order_items", ["planning_version_id"])
    op.create_index(op.f("ix_prd_order_items_product_id"), "prd_order_items", ["product_id"])


def downgrade() -> None:
    op.drop_table("prd_order_items")
    op.drop_table("prd_order_headers")
    op.drop_table("import_errors")
    op.drop_table("import_batches")
    op.drop_table("planning_versions")
    op.drop_table("customers")
    op.drop_table("products")
