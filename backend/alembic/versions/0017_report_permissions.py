"""M6.2 report read permissions; report data remains in domain tables."""
from uuid import UUID, uuid5

from alembic import op
import sqlalchemy as sa

revision = '0017_report_permissions'
down_revision = '0016_grn_imports'
branch_labels = depends_on = None
PERMISSIONS = ('reports.inventory.read', 'reports.purchase.read')


def upgrade():
    permissions = sa.table('permissions', sa.column('id', sa.Uuid()), sa.column('code', sa.String()), sa.column('description', sa.Text()))
    op.bulk_insert(permissions, [{'id': uuid5(UUID('2d98ea56-41e0-40e0-929a-fdf23714891d'), code),
                                 'code': code, 'description': code.replace('.', ' ')} for code in PERMISSIONS])


def downgrade():
    permissions = sa.table('permissions', sa.column('code', sa.String()))
    op.execute(permissions.delete().where(permissions.c.code.in_(PERMISSIONS)))
