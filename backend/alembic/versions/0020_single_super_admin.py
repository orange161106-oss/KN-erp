"""Enforce at most one Super Admin without changing existing accounts."""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "ee17a6e77f73"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("uq_users_single_super_admin", "users", ["is_super_admin"], unique=True,
                    postgresql_where=sa.text("is_super_admin = true"), sqlite_where=sa.text("is_super_admin = 1"))


def downgrade():
    op.drop_index("uq_users_single_super_admin", table_name="users")
