# KNL Consumable ERP backend

Backend/database foundation (M1.1), authentication/RBAC (M1.3), and purchasing
master-data foundation (M2.3), central inventory reporting (M4.1), and projected inventory (M4.2).
Owner: Munees. M1.1 reviewer: Yathish. M1.3 reviewer: Keerthi.

The shared auth schema/API contract is in [docs/13_AUTH_RBAC_CONTRACT.md](../docs/13_AUTH_RBAC_CONTRACT.md).
The master-data contract is in [docs/15_CONSUMABLE_SUPPLIER_MASTER_CONTRACT.md](../docs/15_CONSUMABLE_SUPPLIER_MASTER_CONTRACT.md).
Actual M2.3 validation and reviewer notes are in [M2_3_REVIEW.md](M2_3_REVIEW.md).

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
values use defaults; `DATABASE_URL` and `AUTH_SECRET_KEY` are required for application
startup and cannot remain blank. Schema-only Alembic commands require the database
URL but do not require a signing key.

| Name | Meaning / default |
| --- | --- |
| `APP_NAME` | Application title; `KNL Consumable ERP` |
| `APP_ENV` | `local`, `test`, `staging`, or `production`; default `local` |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`; default `INFO` |
| `DATABASE_URL` | Required PostgreSQL URL; no default |
| `DB_CONNECT_TIMEOUT_SECONDS` | Connection/pool acquisition timeout; integer 1–60, default 5 |
| `TEST_DATABASE_URL` | Test-only disposable PostgreSQL database; read by integration tests |
| `AUTH_SECRET_KEY` | Required operator-generated secret, at least 32 UTF-8 bytes; no default |
| `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES` | Access-token lifetime, integer 1–60; default 15 |
| `AUTH_TOKEN_ISSUER` | Expected JWT issuer; default `kn-consumable-erp` |
| `AUTH_TOKEN_AUDIENCE` | Expected JWT audience; default `kn-consumable-web` |

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
Generate the signing key with a cryptographic secret generator, then supply it
through the local environment/secret store. Do not reuse sample values or database
passwords as signing keys. Startup fails when the key is missing or too short.

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

The existing `0001_backend_foundation` revision remains unchanged and intentionally
empty. The new `0002_auth_rbac` head adds `users`, `roles`, `permissions`, `user_roles`
and `role_permissions`. That auth revision seeds only seven role categories.
The M2.3 revision registers eight master permission codes without assigning them
to any role or creating user accounts. ADMIN has no automatic permission bypass.
Application startup never runs migrations or `metadata.create_all()`.

The current head is `0005_inventory_masters`, following an additive merge of the
existing PRD and plant/process/route migration branches. M2.3 adds `units`,
`consumables`, `suppliers`, `supplier_consumables`, and `audit_logs`. It seeds no
company master records. Existing migration files and business fields are unchanged.
The PostgreSQL Alembic environment accommodates long shared revision IDs with a
128-character version column, widening existing shorter tracking columns. Business
table discovery includes all existing models; product/customer index declarations
match their existing migration rather than generating accidental schema changes.

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
Business endpoints, frontend screens, audit tables and domain rules remain outside
this foundation. The authentication endpoints described below are added in M1.3.
Future business routes must enforce server-side authorization and approved resource
scope checks.

## Authentication and permissions

`POST /api/v1/auth/login` accepts JSON `{username, password}`. Usernames are trimmed
and case-folded; passwords are preserved exactly. Argon2id hashes are verified with
`pwdlib`. Unknown users, wrong passwords and inactive accounts share the same 401
`INVALID_CREDENTIALS` response. There are no default users or passwords.

A successful login returns `access_token`, `token_type: "bearer"`, and `expires_in`
in seconds. Send the token as `Authorization: Bearer <access_token>` when calling
`GET /api/v1/auth/me`. It returns `id`, `username`, sorted `roles`, and sorted
effective `permissions`; password hashes are excluded. Successful auth responses
send `Cache-Control: no-store` and `Pragma: no-cache`.

HTTP bearer authentication is documented in OpenAPI. The login accepts JSON rather
than an OAuth2 password form. In Swagger UI, obtain a token through the login endpoint
and paste it into the bearer Authorize field.

JWT access tokens use a fixed HS256 algorithm and require validated `sub`, `iat`,
`exp`, `iss`, `aud`, and `token_type=access` claims. No permission grants are stored
in the token. The backend reloads the active user and current grants from PostgreSQL
on every authenticated request. Invalid/missing tokens, missing users or inactive
users produce 401 `NOT_AUTHENTICATED`; missing required permissions produce
403 `PERMISSION_DENIED`. Database failures produce 503 `DATABASE_UNAVAILABLE`.

Future routes can use the centralized dependencies:

```python
from typing import Annotated
from fastapi import Depends
from app.schemas.auth import CurrentUser
from app.security.dependencies import get_current_user
from app.security.permissions import require_permissions

# Authentication-only route parameter:
user: Annotated[CurrentUser, Depends(get_current_user)]

# Permission-protected route parameter, using approved permission codes:
user: Annotated[CurrentUser, Depends(require_permissions("<approved-permission-code>"))]
```

`require_permissions` requires every supplied code. Empty requirements are rejected;
unknown/unconfigured permissions deny access. Role/permission assignments remain
data configuration. Initial account provisioning and audited role administration
are TBD, with no public registration or user/role/grant mutation endpoint in M1.3.

Plant access and approval authority remain TBD and need separate resource checks.
Client logout discards the token; there is no refresh or logout-revocation endpoint.
A copied token remains usable until expiry unless its user is deactivated. HTTPS,
login throttling, account recovery and deployment session policy remain deployment
decisions. Keerthi's M1.4 frontend should consume `/auth/me` for navigation permissions
and continue to rely on backend enforcement.

## Consumable, unit and supplier masters

Under `/api/v1/masters`, resources `units`, `consumables`, `suppliers`, and
`supplier-consumables` expose paginated GET collections, GET details, POST create,
PATCH edit, and PATCH `/{id}/status`. Collections return `{items,total,limit,offset}`;
filters include `q`, `is_active`, and mapping supplier/consumable UUIDs.
No DELETE endpoints exist. Every mutation requires `change_reason`; status changes
also require a strict boolean `is_active`. Unknown fields are rejected.

Codes are trimmed/uppercased and unique across active/inactive records. Consumables
require an active unit. Units cannot become inactive while active consumables use
them. Supplier mappings require active suppliers, consumables and units for new use
or reactivation. Inactivation retains references and history. Unit changes on mapped
consumables are blocked pending the approved conversion/history policy.

Each API requires an explicit `masters.<resource>.read` or `.write` grant; use
`supplier_consumables` in permission codes. Permissions are registered by migration
but no role gets them automatically. Read-only users cannot mutate. Provisioning ERP
users and assigning approved grants remains an operator/team prerequisite; there is
no default ERP login or public registration endpoint.

Master writes and audit snapshots commit together. Audit entries record the actor,
action, entity, old/new state, reason, and UTC time. No audit mutation API exists.
Services own transactions; routes remain thin. Supplier lead time, MOQ, pack size,
order multiple, MSQ, conversions and purchase calculations remain TBD/out of scope.

The existing product/customer and PRD routers are now registered in the shared API
router, correcting their pre-existing 404 responses without changing domain logic.
`openpyxl` and `python-multipart` are declared/locked for those existing imports.

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
- Business-domain and worker directories are placeholders. Authentication has its
  own thin module router, schemas, services, repository and security helpers.
  No Celery/Redis or purchase recommendation logic is introduced.

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
application database. Tests create uniquely named `m13_test_*` / `m41_test_*` schemas, apply
migrations there, and remove only that schema at teardown. Synthetic user/grant
changes run inside rollback-only test transactions. Use a dedicated test user with
schema-creation permissions only in the disposable database.

The tests cover settings, secret-safe error responses, health success/failure,
session cleanup, engine shutdown, PostgreSQL connectivity/UTC, uncommitted write
rollback using temporary tables, and baseline upgrade/check/downgrade/re-upgrade.
They also cover auth login/me, malformed/expired/tampered tokens, required claims,
hash exclusion, permission allow/deny, no ADMIN bypass, live grant removal and user
deactivation, authentication constraints, and auth migration upgrade/downgrade.
Migration round trips modify only the isolated test schema in the disposable database.
Never point these tests at shared or production databases.

## Troubleshooting and remaining decisions

- `Invalid backend settings`: set the named fields, particularly `DATABASE_URL` and
  `AUTH_SECRET_KEY` for application startup.
- HTTP 503: check PostgreSQL availability, URL, credentials, database privileges and
  network/TLS configuration. The API intentionally does not echo driver diagnostics.
- `alembic check` reports changes: review model registration/schema drift and add a
  reviewed revision; do not create tables through application startup.
- Integration tests skip: set a process-level `TEST_DATABASE_URL`.
- On Windows, an inaccessible shared pytest temp/cache directory can be avoided with
  `.venv/Scripts/python.exe -m pytest --basetemp=.cache/pytest-tmp -p no:cacheprovider`.
  Create the `.cache` parent directory first. Reserve the temp directory for pytest;
  pytest clears that directory on each run.
- Deployment PostgreSQL version, shared database provisioning, production secrets/TLS,
  account provisioning, audited role administration, permission matrix and session
  requirements remain TBD with the team.

## Framework references

- [SQLAlchemy session lifecycle](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
- [SQLAlchemy Psycopg 3 dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg)
- [Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Pydantic settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [FastAPI password hashing and JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/)
- [PyJWT validation](https://pyjwt.readthedocs.io/en/latest/usage.html)

## Central inventory foundation (M4.1)

Owner: Munees. Reviewer: Keerthi. The
[inventory contract](../docs/17_CENTRAL_INVENTORY_CONTRACT.md) describes the KNL
answers, normalized source format and remaining decisions. The M4.1 revision is
`0011_central_inventory` (parent `0010_requirement_approval`); three append-only source
tables and two unassigned permissions are added. No production accounts or stock
are seeded. Apply and check with the existing configured database:

```powershell
.venv/Scripts/python.exe -m alembic upgrade head
.venv/Scripts/python.exe -m alembic check
.venv/Scripts/python.exe -m alembic current
```

`INVENTORY_IMPORT_ENABLED` defaults to false. Enable it only after verifying the
existing ERP export, usable-stock exclusions and unit/master mapping. There is no
live source connector. The application never posts opening, warehouse movements,
reservations or adjustments; these remain in the existing ERP. All displayed
balances carry source/import timestamps and `is_live=false`. Missing reports are
null, not zero. Source snapshot quantity is authoritative and is not increased
again by source transaction history.

GET `/api/v1/inventory/status`, `/balances`, `/balances/{consumable_id}` and
`/transactions` require `inventory.stock.read`. POST `/api/v1/inventory/imports`
requires `inventory.stock.import` and enabled import configuration. No role bypass
or automatic grants exist. JSON input is limited to 500 movements and 500 snapshots
per export. Each export requires `export_id`, aware `generated_at`, `import_reason`
and at least one source record. Snapshot fields: `source_snapshot_id`, mapped
`consumable_id`, stock `unit_id`, exact string `usable_quantity`, aware `as_of`,
literal `nonusable_excluded=true` and `reservations_excluded=true`. Movement fields:
`source_event_id`, mapped material/stock/source unit UUIDs, exact `source_quantity`,
`movement` (RECEIPT/ISSUE/RETURN), aware `event_at`, `source_actor`, `condition=USABLE`,
and `source_status=POSTED`. Different units also need approved `conversion_factor`
and `conversion_reference`. No business document links are required locally.
OpenAPI provides the full typed schemas. API decimals use strings; never convert
quantities to float. Inexact conversion results are rejected without rounding.

Imports are atomic and audited. Identical export retries return 200 with
`replayed=true`; new imports return 201. Conflicting source identities/timestamps
return 409, and disabled imports return 409. Consumable units cannot change once
stock history/snapshots exist. PostgreSQL triggers reject direct UPDATE/DELETE on
the three source tables. Review downgrade carefully: it drops their history and
requires permission grants to be removed first. Use disposable schemas for tests.

Run `pytest app/tests/test_inventory.py` for API/precision/allow-deny cases and
`pytest app/tests/integration/test_inventory.py` with a dedicated
`TEST_DATABASE_URL` for real concurrent imports and database immutability checks.
Actual results and shared migration fixes are in [M4.1 handoff](M4_1_REVIEW.md).


## Projected inventory foundation (M4.2)

Owner: Munees. Reviewer: Yathish. See the
[projection contract](../docs/18_PROJECTED_INVENTORY_CONTRACT.md) for input semantics,
reconciliation, missing-data behavior and the API explanation. Current Alembic head
is `0012_projected_inventory`. It adds one immutable `projection_input_sets` evidence
table and unassigned `inventory.projection.read` / `inventory.projection.import`
permissions. No business defaults, MSL authority or purchase calculation is seeded.

Use the standard `alembic upgrade head`, `alembic check` and `alembic current`
commands documented above. `PROJECTION_IMPORT_ENABLED` defaults to false. Enable
only after approved source mappings and named technical permissions are configured.

GET `/api/v1/inventory/projections/status` describes capabilities. GET
`/api/v1/inventory/projections` requires `consumable_id`, `planning_version_id` and an
aware `cutoff` timestamp, with optional `source_set_id`. Without complete source
inputs it returns monthly totals, source baseline and explicit limitations; it does
not invent daily demand. An INCOMPLETE response has null projected stock/breach
assessment. Source timestamps and `is_live=false` distinguish dated calculations.

POST `/api/v1/inventory/projections/inputs` stores a normalized evidence set. Full
Pydantic schemas are in OpenAPI. Inputs include source-set identity/reference,
material/stock unit/version/snapshot IDs, reconciliation timestamp/reference and
coverage end. Each plant's explicit fulfilled, reserved and dated remaining demand
must reconcile to its final total. Incoming `scheduled_quantity` is the gross amount
for a unique delivery-schedule identity; `received_quantity` and `cancelled_quantity`
are deducted once. Incoming status and usable-availability time must be supplied.
An empty incoming list confirms none; null means unknown. MSL revisions include
source/approval references and effective times. Optional lead time needs an existing
supplier/material mapping and an approved start-to-usable-availability interval.
Lead time alone never creates incoming stock.

Imports are atomic/audited, immutable and replayable. Conflicting identities return
409. Reads use a consistent PostgreSQL snapshot, validate the current requirement
fingerprint and latest stock identity, and require new reconciliation after either
changes. Existing final-version approval fields must be populated by the upstream
workflow; this module does not grant approval or populate them. Central projection
permissions expose selected-version requirements across plants and must be granted
explicitly to appropriate operators. There are no local MSL edit/delete endpoints.

Run `pytest app/tests/test_projection.py` for the deterministic engine and API cases.
With a dedicated `TEST_DATABASE_URL`, run
`pytest app/tests/integration/test_projection.py` for PostgreSQL immutability,
concurrent input imports and consistency during concurrent requirement changes.
The full suite also validates migration round trips. Actual results are recorded in
[M4.2 reviewer handoff](M4_2_REVIEW.md). M4.4 can consume these explanation APIs for
planning screens and alert presentation after KNL's remaining policies are confirmed.

## Reorder timing foundation (M4.3)

Owner: Munees. Reviewer: Keerthi. POST `/api/v1/inventory/reorder/assess` is a
read-only assessment requiring `inventory.projection.read`. Supply material/version,
source-set identity, aware evaluation/cutoff timestamps and explicit policy/lead-time
evidence. OpenAPI exposes the typed body. The service reads M4.2's stored sources;
it does not trust client-calculated projected stock or add incoming again.

The response returns nullable reorder_required, expected crossing, latest order
deadline/inclusivity and source explanation. Missing timing/policy/calendar/coverage
returns INCOMPLETE, not false. No breach returns false only for a verified horizon
covering the supplied lead time. Already-breached stock requires action without
claiming an order can prevent a past breach. No purchase quantity is calculated.

This is a supplied-evidence assessment, not a policy approval or automatic ordering
endpoint. There is no new migration, environment setting, database write or UI.
Alembic head remains `0012_projected_inventory`. Read the
[timing contract](../docs/19_REORDER_TIMING_CONTRACT.md) before providing calendars
or treating outputs operationally. Run `pytest app/tests/test_reorder.py` and, with
the existing disposable TEST_DATABASE_URL, `pytest app/tests/integration/test_reorder.py`.
Actual results are recorded in [M4.3 reviewer handoff](M4_3_REVIEW.md).
