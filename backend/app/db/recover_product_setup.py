"""Guarded recovery for the inspected missing external migration checkpoint.

Default mode is read-only. --apply requires explicit operator approval and keeps
the schema evidence and previous migration marker in an ignored local backup.
This is a checkpoint reconciliation, not reconstruction of the missing file.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Boolean, inspect, text

from app import models  # noqa: F401
from app.core.config import BACKEND_ROOT, load_settings
from app.db.base import Base
from app.db.session import create_db_engine

EXTERNAL_REVISION = '2994bb185290'
KNOWN_BASELINE = 'ee17a6e77f73'
EXTERNAL_COLUMNS = frozenset({
    'can_access_purchase', 'can_access_prd_planning', 'can_access_production_mappings',
    'can_access_masters', 'can_access_inventory', 'can_access_consumption_norms',
    'can_access_requirements', 'can_access_purchase_orders', 'can_access_goods_receipts',
    'can_access_plant_workflow',
})


def verify_differences(differences):
    required = set()
    preserved = set()
    for difference in differences:
        if not isinstance(difference, tuple):
            raise RuntimeError('Unexpected database change; recovery refused.')
        operation = difference[0]
        if operation == 'add_column' and difference[2] == 'products' and difference[3].name in {'item_id', 'part_number'}:
            required.add(difference[3].name)
        elif operation == 'add_index' and difference[1].table.name == 'users' and difference[1].name == 'uq_users_single_super_admin':
            required.add('uq_users_single_super_admin')
        elif operation == 'remove_column' and difference[2] == 'users' and difference[3].name in EXTERNAL_COLUMNS and isinstance(difference[3].type, Boolean):
            # Comparison reports these as removal candidates. Recovery never drops them.
            preserved.add(difference[3].name)
        else:
            raise RuntimeError('Database differs from the inspected baseline; recovery refused.')
    if required != {'item_id', 'part_number', 'uq_users_single_super_admin'} or preserved != EXTERNAL_COLUMNS:
        raise RuntimeError('Database no longer matches the inspected recovery case; recovery refused.')


def validate(connection):
    revisions = list(connection.execute(text('SELECT version_num FROM alembic_version')).scalars())
    if revisions != [EXTERNAL_REVISION]:
        raise RuntimeError('Unexpected migration checkpoint; recovery refused.')
    if connection.scalar(text('SELECT count(*) FROM users WHERE is_super_admin = true')) != 1:
        raise RuntimeError('Expected exactly one Super Admin; recovery refused.')
    context = MigrationContext.configure(connection, opts={'compare_type': True})
    verify_differences(compare_metadata(context, Base.metadata))
    return revisions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Apply only after explicit approval for shared database recovery.')
    arguments = parser.parse_args()
    engine = create_db_engine(load_settings())
    try:
        with engine.begin() as connection:
            if not arguments.apply:
                connection.execute(text('SET TRANSACTION READ ONLY'))
            else:
                connection.execute(text('SET LOCAL lock_timeout = \'15s\''))
                connection.execute(text('LOCK TABLE alembic_version, users, products IN SHARE ROW EXCLUSIVE MODE'))
            revisions = validate(connection)
            if not arguments.apply:
                print('CHECK PASSED: baseline matches; two product columns and one protection index are pending. Ten external access columns will be preserved. No changes applied.')
                return
            inspector = inspect(connection)
            snapshot = {table: [{'name': c['name'], 'type': str(c['type']), 'nullable': c['nullable'], 'default': c['default']}
                               for c in inspector.get_columns(table)] for table in inspector.get_table_names()}
            destination = BACKEND_ROOT / '.local' / 'migration-recovery'
            destination.mkdir(parents=True, exist_ok=True)
            backup = destination / f"product-setup-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}.json"
            backup.write_text(json.dumps({'previous_revision': revisions, 'known_baseline': KNOWN_BASELINE,
                                          'schema': snapshot, 'preserved_columns': sorted(EXTERNAL_COLUMNS)}, indent=2), encoding='utf-8')
            config = Config(str(BACKEND_ROOT / 'alembic.ini'))
            config.set_main_option('script_location', str(BACKEND_ROOT / 'alembic'))
            config.attributes['connection'] = connection
            command.stamp(config, KNOWN_BASELINE, purge=True)
            command.upgrade(config, '0021')
            final_revision = connection.scalar(text('SELECT version_num FROM alembic_version'))
            columns = {c['name'] for c in inspect(connection).get_columns('products')}
            if final_revision != '0021' or not {'item_id', 'part_number'}.issubset(columns):
                raise RuntimeError('Recovery verification failed; transaction will roll back.')
        print('RECOVERY COMPLETE: migration 0021 applied. No business records were changed. Schema/checkpoint evidence saved locally.')
    except Exception as error:
        # Do not print DB driver exceptions, which can include connection details.
        print(str(error) if isinstance(error, RuntimeError) else f'Recovery failed ({type(error).__name__}); no transaction committed.')
        raise SystemExit(1) from None
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
