"""Track monthly Product Master uploads and join the two existing schema heads.

Revision ID: e002_master_period_uploads
Revises: e001_phase4_product_master_pipeline, 0025_add_item_class_to_stock_statement_lines
"""
from alembic import op
import sqlalchemy as sa

revision = "e002_master_period_uploads"
down_revision = ("e001_phase4_product_master_pipeline", "0025_add_item_class_to_stock_statement_lines")
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("master_upload_batches"):
        expected = {"id", "category", "month", "year", "status", "version", "filename", "records",
                    "created_by", "updated_by", "created_at", "updated_at"}
        if {column["name"] for column in inspector.get_columns("master_upload_batches")} != expected:
            raise RuntimeError("Existing master_upload_batches schema differs; review it before deployment.")
        indexes = inspector.get_indexes("master_upload_batches")
        if not any(index["name"] == "uq_master_upload_active_period" and index["unique"] for index in indexes):
            raise RuntimeError("Existing master_upload_batches period constraint differs; review deployment.")
        return
    op.create_table(
        "master_upload_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("records", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("updated_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_master_upload_batches"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT", name="fk_master_upload_batches_created_by_users"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="RESTRICT", name="fk_master_upload_batches_updated_by_users"),
        sa.CheckConstraint("month BETWEEN 1 AND 12", name=op.f("ck_master_upload_batches_month_range")),
        sa.CheckConstraint("year BETWEEN 2000 AND 2100", name=op.f("ck_master_upload_batches_year_range")),
        sa.CheckConstraint("category IN ('consumables','sales_parts','assemble')", name=op.f("ck_master_upload_batches_category")),
        sa.CheckConstraint("status IN ('active','superseded','deleted')", name=op.f("ck_master_upload_batches_status")),
        sa.CheckConstraint("version >= 1", name=op.f("ck_master_upload_batches_version")),
    )
    op.create_index("uq_master_upload_active_period", "master_upload_batches", ["category", "year", "month"], unique=True,
                    postgresql_where=sa.text("status = 'active'"), sqlite_where=sa.text("status = 'active'"))
    if bind.dialect.name == "postgresql":
        # The application accesses this through its backend connection only.
        op.execute("ALTER TABLE master_upload_batches ENABLE ROW LEVEL SECURITY")


def downgrade():
    op.drop_table("master_upload_batches")
