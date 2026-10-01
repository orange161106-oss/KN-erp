import pytest
from pydantic import ValidationError

from app.core.config import Settings, load_settings

URL = "postgresql://test_user:test_password@127.0.0.1/kn_unit_test"


def test_environment_overrides_dotenv(monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text("APP_ENV=local\nDATABASE_URL=" + URL, encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "test")
    config = Settings(_env_file=dotenv)
    assert config.app_env == "test"
    assert config.sqlalchemy_url.drivername == "postgresql+psycopg"


def test_blank_example_values_use_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    dotenv = tmp_path / ".env"
    dotenv.write_text("APP_ENV=\nLOG_LEVEL=\nDATABASE_URL=" + URL, encoding="utf-8")
    config = Settings(_env_file=dotenv)
    assert config.app_env == "local"
    assert config.log_level == "INFO"
    assert "test_password" not in repr(config)


@pytest.mark.parametrize("url", ["sqlite:///app.db", "invalid", "postgresql:///no_host"])
def test_invalid_database_urls_are_rejected(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=url)


@pytest.mark.parametrize("timeout", [0, -1, 61])
def test_invalid_timeouts_are_rejected(timeout):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=URL, db_connect_timeout_seconds=timeout)


def test_startup_configuration_errors_hide_inputs(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://user:do_not_log_me@host/database")
    with pytest.raises(RuntimeError) as error:
        load_settings()
    assert str(error.value) == "Invalid backend settings: database_url"
    assert "do_not_log_me" not in str(error.value)


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
