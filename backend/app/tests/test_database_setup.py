from unittest.mock import MagicMock

import psycopg
import pytest
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.db import setup


@pytest.fixture
def configuration():
    return Settings(_env_file=None, app_env='local',
                    database_url='postgresql+psycopg://app_user:synthetic-password@localhost:5432/knl_local')


@pytest.fixture
def administration(monkeypatch):
    connection = MagicMock()
    connection.execute.side_effect = lambda *args, **kwargs: MagicMock(fetchone=lambda: (True,))
    connect = MagicMock()
    connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr(setup.psycopg, 'connect', connect)
    upgrade = MagicMock()
    monkeypatch.setattr(setup, 'migrate', upgrade)
    return connection, connect, upgrade


def test_existing_database_is_not_recreated_and_migrations_still_run(configuration, administration):
    connection, connect, upgrade = administration
    assert setup.setup_database(configuration) is False
    assert len(connection.execute.call_args_list) == 2
    upgrade.assert_called_once()
    assert connect.call_args.kwargs['autocommit'] is True
    assert 'hostaddr=127.0.0.1' in connect.call_args.args[0]


def test_missing_database_is_created_with_quoted_name_and_configured_owner(configuration, administration):
    connection, _, upgrade = administration
    connection.execute.side_effect = [MagicMock(fetchone=lambda: (True,)), MagicMock(fetchone=lambda: (False,)), MagicMock()]
    configuration = configuration.model_copy(update={'database_url': setup.SecretStr(
        'postgresql+psycopg://app_user:synthetic-password@localhost/knl"quoted')})
    assert setup.setup_database(configuration) is True
    statement = connection.execute.call_args_list[2].args[0].as_string()
    assert statement == 'CREATE DATABASE "knl""quoted" OWNER "app_user" TEMPLATE template0'
    assert upgrade.call_args.args[0].sqlalchemy_url.database == 'knl"quoted'


@pytest.mark.parametrize('environment,host,database', [
    ('production', 'localhost', 'knl'), ('staging', 'localhost', 'knl'),
    ('local', 'remote.example', 'knl'), ('local', 'localhost', 'postgres'),
    ('local', 'localhost', 'template1'), ('local', 'localhost', 'x' * 64),
])
def test_wrong_target_is_rejected_before_connection_or_prompt(environment, host, database, administration):
    _, connect, upgrade = administration
    settings = Settings(_env_file=None, app_env=environment, database_url=f'postgresql://app_user@{host}/{database}')
    with pytest.raises(setup.SetupError):
        setup.setup_database(settings, admin_user='postgres')
    connect.assert_not_called()
    upgrade.assert_not_called()


def test_connection_query_cannot_override_checked_local_host(configuration, administration):
    configuration = Settings(_env_file=None, database_url='postgresql://app_user@localhost/knl?hostaddr=192.0.2.1')
    with pytest.raises(setup.SetupError, match='query overrides'):
        setup.setup_database(configuration)
    administration[1].assert_not_called()


def test_busy_setup_does_not_create_or_migrate(configuration, administration):
    connection, _, upgrade = administration
    connection.execute.side_effect = [MagicMock(fetchone=lambda: (False,))]
    with pytest.raises(setup.SetupError, match='Another setup'):
        setup.setup_database(configuration)
    assert len(connection.execute.call_args_list) == 1
    upgrade.assert_not_called()


def test_admin_login_prompts_for_password_and_keeps_application_owner(configuration, administration, monkeypatch):
    connection, connect, upgrade = administration
    connection.execute.side_effect = [MagicMock(fetchone=lambda: (True,)), MagicMock(fetchone=lambda: (False,)), MagicMock()]
    prompt = MagicMock(return_value='synthetic-admin-password')
    monkeypatch.setattr(setup.getpass, 'getpass', prompt)
    assert setup.setup_database(configuration, admin_user='postgres')
    prompt.assert_called_once()
    assert 'postgres:synthetic-admin-password@' in connect.call_args.args[0]
    assert 'OWNER "app_user"' in connection.execute.call_args_list[2].args[0].as_string()
    assert upgrade.call_args.args[0].sqlalchemy_url.username == 'app_user'


def test_external_database_creation_race_is_reused(configuration, administration):
    connection, _, upgrade = administration
    connection.execute.side_effect = [MagicMock(fetchone=lambda: (True,)), MagicMock(fetchone=lambda: (False,)), psycopg.errors.DuplicateDatabase()]
    assert setup.setup_database(configuration) is False
    upgrade.assert_called_once()


@pytest.mark.parametrize('failure', [psycopg.OperationalError('synthetic-secret'), psycopg.errors.InsufficientPrivilege('synthetic-secret'),
                                   psycopg.errors.UndefinedObject('synthetic-secret')])
def test_database_errors_do_not_expose_credentials(configuration, administration, failure):
    administration[1].side_effect = failure
    with pytest.raises(setup.SetupError) as error:
        setup.setup_database(configuration)
    assert 'synthetic-secret' not in str(error.value)
    administration[2].assert_not_called()


def test_failed_migration_never_drops_database(configuration, administration):
    connection, _, upgrade = administration
    upgrade.side_effect = OperationalError('statement', {}, Exception('synthetic-secret'))
    with pytest.raises(setup.SetupError) as error:
        setup.setup_database(configuration)
    assert 'synthetic-secret' not in str(error.value)
    assert len(connection.execute.call_args_list) == 2


def test_migrations_use_absolute_paths_and_supplied_transaction(configuration, monkeypatch):
    engine = MagicMock()
    connection = engine.begin.return_value.__enter__.return_value
    monkeypatch.setattr(setup, 'create_db_engine', lambda _: engine)
    upgrade = MagicMock()
    monkeypatch.setattr(setup.command, 'upgrade', upgrade)
    setup.migrate(configuration)
    config, target = upgrade.call_args.args
    assert config.attributes['connection'] is connection and target == 'head'
    assert config.get_main_option('script_location') == str(setup.BACKEND_ROOT / 'alembic')
    engine.dispose.assert_called_once()


def test_successful_command_prints_result_without_url(configuration, monkeypatch, capsys):
    monkeypatch.setattr(setup, 'load_settings', lambda: configuration)
    monkeypatch.setattr(setup, 'setup_database', lambda *args, **kwargs: True)
    assert setup.main([]) == 0
    output = capsys.readouterr().out
    assert 'Database created' in output and 'migrations applied successfully' in output
    assert 'synthetic-password' not in output and 'postgresql' not in output


def test_hosted_migration_never_creates_database(monkeypatch, capsys):
    settings = Settings(_env_file=None, database_url='postgresql://postgres:synthetic-password@db.example.supabase.co/postgres?sslmode=require')
    monkeypatch.setattr(setup, 'load_settings', lambda: settings)
    upgrade = MagicMock()
    create = MagicMock()
    monkeypatch.setattr(setup, 'migrate', upgrade)
    monkeypatch.setattr(setup, 'setup_database', create)
    assert setup.main(['--migrate-only']) == 0
    upgrade.assert_called_once_with(settings)
    create.assert_not_called()
    output = capsys.readouterr().out
    assert 'migrations applied successfully' in output
    assert 'Database created' not in output and 'synthetic-password' not in output


def test_hosted_migration_requires_ssl_before_connecting(monkeypatch):
    settings = Settings(_env_file=None, database_url='postgresql://postgres@db.example.supabase.co/postgres')
    upgrade = MagicMock()
    monkeypatch.setattr(setup, 'migrate', upgrade)
    with pytest.raises(setup.SetupError, match='require SSL'):
        setup.migrate_existing(settings)
    upgrade.assert_not_called()


@pytest.mark.parametrize('diagnostic, expected', [
    ('failed to resolve host synthetic-secret: getaddrinfo failed', 'Cannot reach'),
    ('network unreachable 10051 synthetic-secret', 'Cannot reach'),
    ('password authentication failed synthetic-secret', 'authentication failed'),
    ('permission denied synthetic-secret', 'Migrations did not finish'),
])
def test_migration_failure_is_actionable_and_redacted(configuration, monkeypatch, capsys, diagnostic, expected):
    monkeypatch.setattr(setup, 'load_settings', lambda: configuration)
    monkeypatch.setattr(setup, 'migrate', MagicMock(side_effect=OperationalError('secret-statement', {}, Exception(diagnostic))))
    assert setup.main(['--migrate-only']) == 1
    captured = capsys.readouterr()
    assert expected in captured.err
    assert 'synthetic-secret' not in captured.err and 'secret-statement' not in captured.err
    assert 'successfully' not in captured.out


def test_migration_mode_rejects_local_admin_argument(monkeypatch):
    load = MagicMock()
    monkeypatch.setattr(setup, 'load_settings', load)
    with pytest.raises(SystemExit) as error:
        setup.main(['--migrate-only', '--admin-user', 'postgres'])
    assert error.value.code == 2
    load.assert_not_called()
