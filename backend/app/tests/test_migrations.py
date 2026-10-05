from io import StringIO

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import BACKEND_ROOT
from app.db.base import Base


def test_single_master_head_preserves_existing_branches():
    scripts = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))
    assert scripts.get_heads() == ["0017_report_permissions"]
    assert scripts.get_revision("head").down_revision == "0016_grn_imports"
    assert scripts.get_revision("0014_purchase_approval").down_revision == "0013_inventory_alerts"
    assert scripts.get_revision("0013_inventory_alerts").down_revision == "0012_projected_inventory"
    assert scripts.get_revision("0012_projected_inventory").down_revision == "0011_central_inventory"
    assert scripts.get_revision("0011_central_inventory").down_revision == "0010_requirement_approval"
    assert scripts.get_revision("0010_requirement_approval").down_revision == "0009_plant_workflow"
    assert scripts.get_revision("0009_plant_workflow").down_revision == "0008_calculated_requirements"
    assert scripts.get_revision("0008_calculated_requirements").down_revision == "0007_consumption_norms"
    assert scripts.get_revision("0007_consumption_norms").down_revision == "0006_production_consumable_mappings"
    assert scripts.get_revision("0006_production_consumable_mappings").down_revision == "0005_inventory_masters"
    assert scripts.get_revision("0005_inventory_masters").down_revision == "0004_merge_master_heads"
    assert set(scripts.get_revision("0004_merge_master_heads").down_revision) == {"0003_product_customer_prd_staging", "acfaead772de"}
    assert scripts.get_revision("0002_auth_rbac").down_revision == "0001_backend_foundation"
    assert scripts.get_revision("0001_backend_foundation").down_revision is None
    assert {"users", "roles", "permissions", "user_roles", "role_permissions", "units", "consumables", "suppliers", "supplier_consumables", "audit_logs", "products", "plants", "prd_order_items", "consumption_norms", "calculated_requirements", "requirement_calculation_errors"} <= set(Base.metadata.tables)


def test_offline_auth_migration_sql_and_no_secret_required(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test_user:private_password@127.0.0.1/kn_unit_test")
    monkeypatch.delenv("AUTH_SECRET_KEY", raising=False)
    output = StringIO()
    config = Config(str(BACKEND_ROOT / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE alembic_version" in sql
    assert sql.count("CREATE TABLE") == len(Base.metadata.tables) + 1
    assert "0001_backend_foundation" in sql
    assert "0002_auth_rbac" in sql
    assert "0005_inventory_masters" in sql
    assert "0007_consumption_norms" in sql
    assert "0008_calculated_requirements" in sql
    assert "0011_central_inventory" in sql
    assert "CREATE FUNCTION inventory_append_only" in sql
    assert "version_num VARCHAR(128)" in sql
    assert "private_password" not in sql


def test_offline_upgrade_from_existing_foundation_widens_version_column(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test_user@127.0.0.1/kn_unit_test")
    output = StringIO()
    config = Config(str(BACKEND_ROOT / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "0002_auth_rbac:head", sql=True)
    sql = output.getvalue()
    assert sql.index("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)") < sql.index("0003_product_customer_prd_staging")
