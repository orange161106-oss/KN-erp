import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect

from app.core.config import BACKEND_ROOT

pytestmark = pytest.mark.integration


def test_migration_round_trip_and_no_business_tables(postgres_engine):
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with postgres_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert MigrationContext.configure(connection).get_current_heads() == ("0001_backend_foundation",)
        assert inspect(connection).get_table_names() == ["alembic_version"]
        command.check(config)
        command.downgrade(config, "base")
        assert MigrationContext.configure(connection).get_current_heads() == ()
        command.upgrade(config, "head")
        assert MigrationContext.configure(connection).get_current_heads() == ("0001_backend_foundation",)
