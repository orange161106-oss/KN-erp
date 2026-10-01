import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from app.core.config import BACKEND_ROOT

pytestmark = pytest.mark.integration


def test_auth_migration_round_trip_and_empty_grants(postgres_engine):
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with postgres_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert MigrationContext.configure(connection).get_current_heads() == ("0002_auth_rbac",)
        assert set(inspect(connection).get_table_names()) == {"alembic_version", "users", "roles", "permissions", "user_roles", "role_permissions"}
        role_ids = dict(connection.execute(text("SELECT code, id FROM roles")).all())
        assert set(role_ids) == {"ADMIN", "PLANNER", "PLANT_INCHARGE", "STORE", "PURCHASE", "APPROVER", "MANAGEMENT"}
        for table in ("users", "permissions", "user_roles", "role_permissions"):
            assert connection.execute(text("SELECT COUNT(*) FROM " + table)).scalar_one() == 0
        command.check(config)
        command.downgrade(config, "0001_backend_foundation")
        assert inspect(connection).get_table_names() == ["alembic_version"]
        assert MigrationContext.configure(connection).get_current_heads() == ("0001_backend_foundation",)
        command.downgrade(config, "base")
        assert MigrationContext.configure(connection).get_current_heads() == ()
        command.upgrade(config, "head")
        assert MigrationContext.configure(connection).get_current_heads() == ("0002_auth_rbac",)
        assert dict(connection.execute(text("SELECT code, id FROM roles")).all()) == role_ids
        command.check(config)
