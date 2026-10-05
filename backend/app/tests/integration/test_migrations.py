import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from app.core.config import BACKEND_ROOT
from app.db.base import Base

pytestmark = pytest.mark.integration


def test_auth_migration_round_trip_and_empty_grants(postgres_engine):
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with postgres_engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        assert MigrationContext.configure(connection).get_current_heads() == ("0016_grn_imports",)
        assert set(inspect(connection).get_table_names()) == {"alembic_version", *Base.metadata.tables}
        role_ids = dict(connection.execute(text("SELECT code, id FROM roles")).all())
        assert set(role_ids) == {"ADMIN", "PLANNER", "PLANT_INCHARGE", "STORE", "PURCHASE", "APPROVER", "MANAGEMENT"}
        assert connection.execute(text("SELECT COUNT(*) FROM permissions")).scalar_one() == 28
        assert set(connection.execute(text("SELECT code FROM permissions WHERE code LIKE 'purchase.%'")).scalars()) == {'purchase.grns.read', 'purchase.grns.import', 'purchase.orders.read', 'purchase.orders.create', 'purchase.orders.issue', 'purchase.orders.cancel', 'purchase.orders.price', 'purchase.demand.submit'}
        assert set(connection.execute(text("SELECT code FROM permissions WHERE code LIKE 'alerts:%'")).scalars()) == {"alerts:view", "alerts:acknowledge"}
        assert set(connection.execute(text("SELECT code FROM permissions WHERE code LIKE 'inventory.%'")).scalars()) == {"inventory.stock.read", "inventory.stock.import", "inventory.projection.read", "inventory.projection.import"}
        for table in ("users", "user_roles", "role_permissions", "units", "consumables", "suppliers", "supplier_consumables", "audit_logs", "stock_import_batches", "stock_transactions", "stock_snapshots", "projection_input_sets", "inventory_alerts", "purchase_approvals", "purchase_orders", "purchase_order_items", "purchase_demand_evidence", "grns", "grn_items"):
            assert connection.execute(text("SELECT COUNT(*) FROM " + table)).scalar_one() == 0
        command.check(config)
        command.downgrade(config, "0001_backend_foundation")
        assert inspect(connection).get_table_names() == ["alembic_version"]
        assert MigrationContext.configure(connection).get_current_heads() == ("0001_backend_foundation",)
        connection.execute(text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32)"))
        command.upgrade(config, "head")
        assert next(column for column in inspect(connection).get_columns("alembic_version") if column["name"] == "version_num")["type"].length == 128
        command.downgrade(config, "0001_backend_foundation")
        command.downgrade(config, "base")
        assert MigrationContext.configure(connection).get_current_heads() == ()
        command.upgrade(config, "head")
        assert MigrationContext.configure(connection).get_current_heads() == ("0016_grn_imports",)
        assert dict(connection.execute(text("SELECT code, id FROM roles")).all()) == role_ids
        command.check(config)
