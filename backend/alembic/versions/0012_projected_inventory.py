"""M4.2 immutable source evidence for projected inventory."""
from uuid import NAMESPACE_URL, uuid5

from alembic import op
import sqlalchemy as sa

revision = '0012_projected_inventory'
down_revision = '0011_central_inventory'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('projection_input_sets',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('source_set_id', sa.String(192), nullable=False),
        sa.Column('consumable_id', sa.Uuid(), nullable=False),
        sa.Column('planning_version_id', sa.Uuid(), nullable=False),
        sa.Column('stock_snapshot_id', sa.Uuid(), nullable=False),
        sa.Column('payload_hash', sa.String(64), nullable=False),
        sa.Column('requirement_fingerprint', sa.String(64), nullable=False),
        sa.Column('requirement_manifest', sa.JSON(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('imported_by', sa.Uuid(), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_projection_input_sets')),
        sa.UniqueConstraint('source_set_id', name=op.f('uq_projection_input_sets_source_set_id')),
        *[sa.ForeignKeyConstraint([column], [target + '.id'], ondelete='RESTRICT',
                                 name=op.f('fk_projection_input_sets_' + column + '_' + target))
          for column, target in [('consumable_id', 'consumables'), ('planning_version_id', 'planning_versions'),
                                 ('stock_snapshot_id', 'stock_snapshots'), ('imported_by', 'users')]])
    op.create_index('ix_projection_input_sets_consumable_id', 'projection_input_sets', ['consumable_id'])
    op.execute('CREATE TRIGGER projection_input_sets_immutable BEFORE UPDATE OR DELETE ON projection_input_sets FOR EACH ROW EXECUTE FUNCTION inventory_append_only()')
    permissions = sa.table('permissions', sa.column('id', sa.Uuid()), sa.column('code', sa.String()), sa.column('description', sa.Text()))
    op.bulk_insert(permissions, [
        {'id': uuid5(NAMESPACE_URL, 'kn-consumable-erp:permission:' + code), 'code': code, 'description': description}
        for code, description in [('inventory.projection.read', 'Read central projections across plants for a selected version'),
                                  ('inventory.projection.import', 'Import normalized approved projection source evidence')]])


def downgrade():
    permissions = sa.table('permissions', sa.column('code', sa.String()))
    op.execute(permissions.delete().where(permissions.c.code.in_(['inventory.projection.read', 'inventory.projection.import'])))
    op.drop_table('projection_input_sets')
