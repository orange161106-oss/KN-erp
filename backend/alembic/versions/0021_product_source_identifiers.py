"""Retain both identifiers supplied by the existing ERP."""
from alembic import op
import sqlalchemy as sa
revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("products", sa.Column("item_id", sa.String(128), nullable=True))
    op.add_column("products", sa.Column("part_number", sa.String(128), nullable=True))


def downgrade():
    op.drop_column("products", "part_number")
    op.drop_column("products", "item_id")
