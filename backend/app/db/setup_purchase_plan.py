"""Explicit additive setup for purchase proposals, without rewriting external migration history."""
import argparse
from importlib.util import module_from_spec, spec_from_file_location

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from app.core.config import BACKEND_ROOT, load_settings
from app.db.session import create_db_engine


def deploy(connection, apply=False):
    inspector = inspect(connection)
    for table in ('planning_versions', 'consumables', 'units', 'users'):
        columns = {column['name'] for column in inspector.get_columns(table)}
        if 'id' not in columns:
            raise RuntimeError('Required reference schema is unavailable; no changes applied.')
    revisions = list(connection.scalars(text('SELECT version_num FROM alembic_version')))
    if inspector.has_table('purchase_plan_drafts'):
        expected = {'id', 'planning_version_id', 'consumable_id', 'unit_id', 'requested_qty', 'notes', 'version', 'updated_by', 'updated_at'}
        if {column['name'] for column in inspector.get_columns('purchase_plan_drafts')} != expected:
            raise RuntimeError('An incompatible draft table exists; no changes applied.')
        return {'ready': True, 'created': False, 'revisions_preserved': revisions}
    if not apply:
        return {'ready': False, 'created': False, 'revisions_preserved': revisions}
    path = BACKEND_ROOT / 'alembic' / 'versions' / 'c003_purchase_plan_drafts.py'
    spec = spec_from_file_location('purchase_plan_migration', path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    with Operations.context(MigrationContext.configure(connection)):
        migration.upgrade()
    if list(connection.scalars(text('SELECT version_num FROM alembic_version'))) != revisions:
        raise RuntimeError('Unexpected migration-marker change; rolling back.')
    return {'ready': True, 'created': True, 'revisions_preserved': revisions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Create only the reviewed empty purchase draft table.')
    args = parser.parse_args()
    engine = create_db_engine(load_settings())
    try:
        with engine.begin() as connection:
            if connection.dialect.name == 'postgresql':
                connection.execute(text('SELECT pg_advisory_xact_lock(163102026)'))
            result = deploy(connection, args.apply)
        print(result)
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
