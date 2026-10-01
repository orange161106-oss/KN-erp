# KN Consumable ERP backend

M1.1 backend and database foundation. Owner: Munees. Reviewer: Yathish.

## Requirements and installation

- Python 3.12 or newer, and `uv` for reproducible dependency installation.
- A supported PostgreSQL server and an existing database/user with migration permissions.
- Run commands below from `backend/`.

```powershell
uv sync --frozen --extra test
Copy-Item .env.example .env
```

`uv.lock` pins the complete dependency graph. The application uses synchronous
SQLAlchemy 2.0 with Psycopg 3. Starlette remains below 1.0 to retain HTTPX TestClient
compatibility. To intentionally refresh dependencies, use `uv lock`, synchronize,
and repeat the complete validation before review.

## Configuration

Edit the ignored `backend/.env` locally, or supply process environment variables.
The example file deliberately contains names with blank values only. Blank optional
values use defaults; `DATABASE_URL` is required and cannot remain blank.

| Name | Meaning / default |
| --- | --- |
| `APP_NAME` | Application title; `KN Consumable ERP` |
| `APP_ENV` | `local`, `test`, `staging`, or `production`; default `local` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; default `INFO` |
| `DATABASE_URL` | Required PostgreSQL URL; no default |
| `DB_CONNECT_TIMEOUT_SECONDS` | Connection/pool acquisition timeout; integer 1–60, default 5 |
| `TEST_DATABASE_URL` | Test-only disposable PostgreSQL database; read by integration tests |

Connection URL format:
`postgresql+psycopg://<username>:<url-encoded-password>@<host>:<port>/<database>`.
Plain `postgresql://` is also accepted and selects Psycopg 3. Encode reserved
characters in credentials. For TLS, configure PostgreSQL and the appropriate
connection parameters such as `sslmode`; production credentials/TLS policy are TBD.

Explicit settings arguments (used in tests) override process environment variables,
which override `backend/.env`, which overrides defaults. The `.env` path is resolved
relative to this backend directory, independently of the caller's working directory.
Unknown dotenv entries are ignored so shared local configuration can coexist.
`TEST_DATABASE_URL` is not used by the running application.

Database URLs use a secret type and are omitted from application logs/errors.
Invalid startup settings report field names only. No real credentials belong in
tracked files. Sessions configure the PostgreSQL timezone to UTC.

## Database migrations

Create the application database/user using your PostgreSQL administration process;
this backend does not create databases or provision system services.

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic current
.venv/Scripts/python.exe -m alembic heads
.venv/Scripts/python.exe -m alembic check
```

On Linux/macOS, replace `.venv/Scripts/python.exe` with `.venv/bin/python`.
Alternatively, `uv run --frozen --no-sync` can invoke the installed tools.

The single `0001_backend_foundation` revision is intentionally empty. An upgrade
creates only Alembic's `alembic_version` table. There are no business tables.
Application startup never runs migrations or `metadata.create_all()`.

For future models, use `app.db.base.Base`, import model modules in
`app/models/__init__.py`, then generate a new revision:

```powershell
.venv/Scripts/python.exe -m alembic revision --autogenerate -m "describe schema change"
```

Review generated migrations, agree shared schema changes with the relevant owners,
and retain one clean head. Never edit an applied/shared migration. The metadata
defines constraint naming; explicitly name check constraints. Use UTC timestamps
and PostgreSQL `NUMERIC` / Python `Decimal` for precise future business values.

## Start and health contract

```powershell
.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

The engine is initialized during application startup and disposed on shutdown.
Connections are lazy: valid settings allow startup when PostgreSQL is temporarily
unavailable, while the health endpoint reports HTTP 503. This endpoint is a
database readiness check, so successful startup alone does not prove connectivity.

`GET /api/v1/health` executes `SELECT 1` through a service and repository.

- HTTP 200: `{"status":"ok","database":"ok"}`.
- HTTP 503: `{"code":"DATABASE_UNAVAILABLE","message":"Database is unavailable.","details":{}}`.

The endpoint is public and exposes no credentials, hostnames or database names.
Business endpoints, authentication, permission checks, frontend screens, audit
tables and domain rules are outside M1.1. Future business routes must enforce
server-side authorization.

## Shared conventions

- Routes validate/serialize and call services. Repositories contain persistence only.
- `get_db` provides a request-scoped session. Sessions always close and roll back on
  failure. They also discard uncommitted work on normal exit; they never auto-commit.
- Application services own explicit transaction boundaries. Prefer
  `with session.begin():` for coordinated writes; routes must not commit.
- All API errors use `code`, `message`, `details`. Validation errors use
  `VALIDATION_ERROR` (422) with locations/types, omitting submitted values.
  HTTP errors use `HTTP_ERROR`; unexpected failures use `INTERNAL_SERVER_ERROR`
  (500) with a generic message. HTTP exception headers are preserved.
- Application log events are JSON with UTC timestamp, level, logger and event.
  PostgreSQL failures log a fixed event, without exception text or SQL parameters.
- Business-domain and worker directories are placeholders. No Celery/Redis,
  inventory/purchasing logic or business tables are introduced.

## Tests

Tests that do not need PostgreSQL:

```powershell
.venv/Scripts/python.exe -m pytest -m "not integration"
```

For full validation, provision a separate, disposable database whose name ends in
`_test`. Set `TEST_DATABASE_URL` in the process environment, then run:

```powershell
.venv/Scripts/python.exe -m pytest
```

Integration tests read `TEST_DATABASE_URL` from the process environment, rather than
loading it from `.env`. Without it they explicitly skip. A configured but unreachable
test server causes failure, not a skip. The test database must differ from the
application database and contain no public tables except an existing Alembic version
table. These safeguards support repeated local validation; use a dedicated test user
with access only to the disposable database.

The tests cover settings, secret-safe error responses, health success/failure,
session cleanup, engine shutdown, PostgreSQL connectivity/UTC, uncommitted write
rollback using temporary tables, and baseline upgrade/check/downgrade/re-upgrade.
Migration round trips modify only the disposable database. Never point these tests
at shared, production, or business-data databases.

## Troubleshooting and remaining decisions

- `Invalid backend settings`: set the named fields, particularly `DATABASE_URL`.
- HTTP 503: check PostgreSQL availability, URL, credentials, database privileges and
  network/TLS configuration. The API intentionally does not echo driver diagnostics.
- `alembic check` reports changes: review model registration/schema drift and add a
  reviewed revision; do not create tables through application startup.
- Integration tests skip: set a process-level `TEST_DATABASE_URL`.
- On Windows, an inaccessible shared pytest temp/cache directory can be avoided with
  `.venv/Scripts/python.exe -m pytest --basetemp=.cache/pytest-tmp -p no:cacheprovider`.
  Reserve that directory for pytest; pytest clears its temporary directory on each run.
- Deployment PostgreSQL version, shared database provisioning, production secrets/TLS,
  and authentication contracts remain TBD with the team.

## Framework references

- [SQLAlchemy session lifecycle](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
- [SQLAlchemy Psycopg 3 dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg)
- [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Pydantic settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
