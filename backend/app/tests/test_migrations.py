from io import StringIO

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.core.config import BACKEND_ROOT
from app.db.base import Base


def test_single_empty_baseline_head():
    scripts = ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini")))
    assert scripts.get_heads() == ["0001_backend_foundation"]
    assert scripts.get_revision("head").down_revision is None
    assert not Base.metadata.tables


def test_offline_migration_sql_contains_only_version_table(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://test_user:private_password@127.0.0.1/kn_unit_test")
    output = StringIO()
    config = Config(str(BACKEND_ROOT / "alembic.ini"), output_buffer=output)
    command.upgrade(config, "head", sql=True)
    sql = output.getvalue()
    assert "CREATE TABLE alembic_version" in sql
    assert sql.count("CREATE TABLE") == 1
    assert "0001_backend_foundation" in sql
    assert "private_password" not in sql
