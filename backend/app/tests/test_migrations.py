from io import StringIO

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import BACKEND_ROOT
from app.db.base import Base


def test_single_auth_head_preserves_existing_baseline():
    scripts = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))
    assert scripts.get_heads() == ["0002_auth_rbac"]
    assert scripts.get_revision("head").down_revision == "0001_backend_foundation"
    assert scripts.get_revision("0001_backend_foundation").down_revision is None
    assert set(Base.metadata.tables) == {"users", "roles", "permissions", "user_roles", "role_permissions"}


def test_offline_auth_migration_sql_and_no_secret_required(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test_user:private_password@127.0.0.1/kn_unit_test")
    monkeypatch.delenv("AUTH_SECRET_KEY", raising=False)
    output = StringIO()
    config = Config(str(BACKEND_ROOT / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE alembic_version" in sql
    assert sql.count("CREATE TABLE") == 6
    assert "0001_backend_foundation" in sql
    assert "0002_auth_rbac" in sql
    assert "private_password" not in sql
