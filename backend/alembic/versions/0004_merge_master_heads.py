"""Join the existing PRD and production-master migration branches."""

revision = "0004_merge_master_heads"
down_revision = ("0003_product_customer_prd_staging", "acfaead772de")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
