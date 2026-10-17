"""Explicit additive deployment when a database has unavailable Alembic ancestry.

Creates only the monthly Product Master upload table using its frozen migration.
Does not stamp Alembic or touch existing master/business/permission rows.
Run from backend: python -m app.db.setup_master_uploads
"""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.core.config import load_settings
from app.db.session import create_db_engine


def main():
    path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "e002_master_period_uploads.py"
    spec = spec_from_file_location("master_upload_migration", path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_db_engine(load_settings())
    try:
        with engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SELECT pg_advisory_xact_lock(145102026)"))
            before = list(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            after = list(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
            if before != after:
                raise RuntimeError("Alembic revision changed unexpectedly; rolling back.")
        print("Monthly Product Master upload storage is ready. Existing data and migration revision preserved.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
