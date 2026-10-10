"""Explicit local creation or migrations for an existing database; never run on startup."""
import argparse
import getpass
import hashlib
import sys

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError
import psycopg
from psycopg import sql
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import BACKEND_ROOT, Settings, load_settings
from app.db.session import create_db_engine

LOCAL_HOSTS = {'localhost': '127.0.0.1', '127.0.0.1': '127.0.0.1', '::1': '::1'}
SYSTEM_DATABASES = {'postgres', 'template0', 'template1'}
TARGET_OVERRIDES = {'host', 'hostaddr', 'port', 'dbname', 'database', 'user', 'password', 'service', 'servicefile'}


class SetupError(Exception):
    """Operator-facing explanation without connection credentials."""


def local_settings(settings: Settings) -> Settings:
    url = settings.sqlalchemy_url
    host = (url.host or '').lower()
    if settings.app_env != 'local' or host not in LOCAL_HOSTS:
        raise SetupError('Database creation requires APP_ENV=local and a localhost DATABASE_URL. For an existing hosted database, use --migrate-only.')
    if url.database.lower() in SYSTEM_DATABASES:
        raise SetupError('DATABASE_URL must name your application database, not postgres/template0/template1.')
    if TARGET_OVERRIDES.intersection(key.lower() for key in url.query):
        raise SetupError('Put the connection host, port, user and database in DATABASE_URL, not query overrides.')
    if len(url.database.encode('utf-8')) > 63:
        raise SetupError('The database name must fit PostgreSQL\'s 63-byte identifier limit.')
    # Pin both administration and migration connections to the loopback address,
    # even if libpq environment variables or DNS supply a different host address.
    url = url.update_query_dict({'hostaddr': LOCAL_HOSTS[host]})
    return settings.model_copy(update={'database_url': SecretStr(url.render_as_string(hide_password=False))})


def migrate(settings: Settings) -> None:
    engine = create_db_engine(settings)
    try:
        config = Config(str(BACKEND_ROOT / 'alembic.ini'))
        config.set_main_option('script_location', str(BACKEND_ROOT / 'alembic'))
        with engine.begin() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, 'head')
    finally:
        engine.dispose()


def migrate_existing(settings: Settings) -> None:
    """Apply existing revisions without creating, dropping or resetting a database."""
    url = settings.sqlalchemy_url
    if (url.host or '').lower() not in LOCAL_HOSTS and url.query.get('sslmode') not in {'require', 'verify-ca', 'verify-full'}:
        raise SetupError('Hosted database migrations require SSL. Add sslmode=require (or certificate verification) to DATABASE_URL.')
    try:
        migrate(settings)
    except (psycopg.Error, SQLAlchemyError) as error:
        # Inspect driver diagnostics but never echo them: they may contain secrets.
        diagnostic = str(getattr(error, 'orig', error)).lower()
        if any(term in diagnostic for term in ('resolve host', 'getaddrinfo', 'network is unreachable', 'network unreachable', '10051')):
            raise SetupError('Cannot reach the database hostname. Check the copied hostname and network. Supabase direct connections need working IPv6 or its IPv4 add-on; migration code cannot provide network access. No successful migration was confirmed.') from None
        if 'password authentication failed' in diagnostic:
            raise SetupError('Database authentication failed. Check the database username and URL-encoded password privately in .env.') from None
        raise SetupError('Migrations did not finish. Check database connectivity, credentials and migration permissions. The database is not reset.') from None
    except CommandError:
        raise SetupError('Alembic migration configuration failed. Check revision history; do not reset or stamp the database to bypass the error.') from None


def setup_database(settings: Settings, *, admin_user: str | None = None) -> bool:
    settings = local_settings(settings)
    target = settings.sqlalchemy_url
    admin = target.set(drivername='postgresql', database='postgres')
    if admin_user is not None:
        if not admin_user.strip():
            raise SetupError('The administration username must not be blank.')
        admin = admin.set(username=admin_user, password=getpass.getpass('Local PostgreSQL admin password: '))
    lock_id = int.from_bytes(hashlib.sha256(('knl-database-setup:' + target.database).encode()).digest()[:8], 'big', signed=True)
    try:
        # CREATE DATABASE cannot run in a transaction. Session-level advisory
        # locking serializes this tool's creation and migration for the same DB.
        with psycopg.connect(admin.render_as_string(hide_password=False), autocommit=True,
                             connect_timeout=settings.db_connect_timeout_seconds) as connection:
            if not connection.execute('SELECT pg_try_advisory_lock(%s)', (lock_id,)).fetchone()[0]:
                raise SetupError('Another setup command is running for this database. Retry after it finishes.')
            exists = connection.execute('SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = %s)',
                                        (target.database,)).fetchone()[0]
            if not exists:
                # Identifier quoting is essential: database/role names are not SQL values.
                statement = sql.SQL('CREATE DATABASE {} OWNER {} TEMPLATE template0').format(
                    sql.Identifier(target.database), sql.Identifier(target.username))
                try:
                    connection.execute(statement)
                except psycopg.errors.DuplicateDatabase:
                    # A separate administration tool may have created it meanwhile.
                    exists = True
            migrate(settings)
            return not exists
    except psycopg.errors.InsufficientPrivilege:
        raise SetupError('Database creation needs a PostgreSQL admin or CREATEDB privilege. Retry with --admin-user postgres.') from None
    except psycopg.errors.UndefinedObject:
        raise SetupError('The DATABASE_URL user must already exist in PostgreSQL. This command does not create or change login credentials.') from None
    except (psycopg.Error, SQLAlchemyError):
        raise SetupError('Database setup did not finish. Check the local PostgreSQL service, credentials and migration permissions; rerun after correcting them. Existing data is not reset.') from None
    except CommandError:
        raise SetupError('Alembic upgrade did not finish. Check the migration configuration and rerun; the database is not dropped.') from None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admin-user', help='Optional local admin login; password is prompted securely, not passed on the command line')
    parser.add_argument('--migrate-only', action='store_true', help='Apply Alembic to an already provisioned database, including Supabase; never create a database')
    args = parser.parse_args(argv)
    if args.migrate_only and args.admin_user:
        parser.error('--admin-user is only for local database creation, not --migrate-only')
    try:
        settings = load_settings()
    except RuntimeError as error:
        # load_settings exposes only invalid field names, never their values.
        print(str(error), file=sys.stderr)
        return 1
    try:
        if args.migrate_only:
            migrate_existing(settings)
            created = None
        else:
            created = setup_database(settings, admin_user=args.admin_user)
    except (SetupError, EOFError, KeyboardInterrupt) as error:
        message = str(error) if isinstance(error, SetupError) else 'Setup cancelled; no database reset was performed.'
        print(message, file=sys.stderr)
        return 1
    if created is not None:
        print('Database created.' if created else 'Database already exists; reused.')
    print('Alembic migrations applied successfully. You can now start the backend.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
