# M1.3 authentication and RBAC review handoff

Owner: Munees. Reviewer: Keerthi.
Branch: `feature/munees/m1.3-auth-rbac-backend`, based on local `develop` containing M1.1/M1.2.
Status: review-ready, uncommitted working tree. No push, PR creation or merge performed.

## Delivered behavior

- Users, roles, permissions and their two association tables share the existing
  SQLAlchemy Base. Usernames are normalized and unique; timestamps are UTC.
- Passwords use salted Argon2id hashes with pwdlib. Responses omit password hashes.
- JSON login issues a short-lived signed JWT. Current-user loads the active account
  and current role/permission grants from PostgreSQL on each authenticated request.
- Centralized `get_current_user`, `check_permissions` and `require_permissions`
  provide authentication and all-required-permission checks.
- Missing/ungranted permissions deny access. ADMIN has no automatic bypass.
- Known role categories are seeded without grants. No KN-specific approval limits,
  authority matrix, plant policy or business permissions were invented.

## Migration and API impact

New revision: `0002_auth_rbac`, following the unchanged `0001_backend_foundation`.
Tables added: `users`, `roles`, `permissions`, `user_roles`, `role_permissions`.
Seeded categories: ADMIN, PLANNER, PLANT_INCHARGE, STORE, PURCHASE, APPROVER, MANAGEMENT.
No accounts, permissions, or role grants are seeded. Unique pairs and foreign keys
protect associations; referenced entities use RESTRICT foreign keys.

APIs added:

- `POST /api/v1/auth/login`: JSON username/password; response access token, bearer type,
  and lifetime in seconds. Unknown account, wrong password and inactive account
  all return generic 401 `INVALID_CREDENTIALS`.
- `GET /api/v1/auth/me`: bearer authentication; response ID, normalized username,
  sorted roles and effective permission codes. Invalid authentication returns
  401 `NOT_AUTHENTICATED` with `WWW-Authenticate: Bearer`.

The shared permission dependency returns 403 `PERMISSION_DENIED`. PostgreSQL failures
return 503 `DATABASE_UNAVAILABLE`. All retain the existing error envelope. Successful
auth responses send no-store/no-cache headers. Existing health behavior is preserved.

Application startup now requires `AUTH_SECRET_KEY`, an operator-generated signing
secret of at least 32 UTF-8 bytes with no default. Schema-only migrations do not
require this key. Tokens use a fixed HS256 algorithm and validate required identity,
expiry, issued-at, issuer, audience and token-type claims. Lifetime defaults to
15 minutes and can be configured from 1 to 60 minutes.

## Actual validation results

Environment: Python 3.12.14, PostgreSQL 17.11, pwdlib 0.3.1, Argon2-cffi 25.1.0,
PyJWT 2.15.1. Database URLs and random signing secrets were supplied through the
process environment, not committed.

Unit/API checks without PostgreSQL:

```text
.venv/Scripts/python.exe -m pytest -m "not integration" -p no:cacheprovider --basetemp=C:/KN/backend/.local/pytest-unit-tmp
72 passed, 18 deselected, 1 warning in 5.28s
```

Full backend suite, with an explicitly configured disposable PostgreSQL test database:

```text
.venv/Scripts/python.exe -m pytest --basetemp=C:/KN/.cache/postgres-validation/m13-pytest-tmp -p no:cacheprovider
90 passed, 1 warning in 6.95s
```

All 18 integration checks ran; none skipped. Coverage includes:

- Real login/current-user requests against PostgreSQL and hash exclusion.
- Permission union across roles, all-required grants, unknown permissions and unauthenticated denial.
- Existing-token rejection after user deactivation and immediate deny after grant/role removal.
- ADMIN denial without an explicit grant.
- Database username/role/permission uniqueness, association uniqueness, FK enforcement,
  normalized username enforcement and UTC timestamps.
- Migration upgrade/check/downgrade to M1.1/base/re-upgrade; stable seeded role IDs.
- Existing engine/session cleanup, health and transaction rollback checks.
- Invalid token signatures, algorithms, tampering, expiration, future issued-at time,
  invalid issuer/audience/subject/type and every missing required claim.

The remaining warning is the existing Starlette/AnyIO `BlockingPortal` deprecation.
An initial unit invocation had two temporary-directory setup errors because its parent
directory did not exist; creating that parent resolved both before the reported passes.

Migration command output against the disposable application database:

```text
python -m alembic upgrade head
exit 0

python -m alembic current
0002_auth_rbac (head)

python -m alembic heads
0002_auth_rbac (head)

python -m alembic check
No new upgrade operations detected.
```

Direct inspection after upgrade:

```text
Application tables: ['alembic_version', 'permissions', 'role_permissions', 'roles', 'user_roles', 'users']
Seeded role categories: 7
Seeded users: 0
Seeded permissions: 0
Seeded grants: 0
```

Python compilation and Git whitespace checks passed. `.env.example` contains ten
blank variable assignments only. The existing baseline migration was not changed.
Integration data is isolated in uniquely named temporary schemas and rollback-only
transactions. The temporary PostgreSQL instance was stopped after validation.

## Files changed

Added:

- `docs/13_AUTH_RBAC_CONTRACT.md` and `backend/M1_3_REVIEW.md`.
- `backend/alembic/versions/0002_auth_rbac.py`.
- `backend/app/models/auth.py`, `schemas/auth.py`, `repositories/auth.py`,
  `services/auth.py`, `modules/auth/router.py`.
- `backend/app/security/identity.py`, `passwords.py`, `tokens.py`, `dependencies.py`,
  `permissions.py`.
- `backend/app/tests/test_auth.py`, `test_passwords.py`,
  `backend/app/tests/integration/test_auth.py`.

Updated:

- `docs/README.md`, `backend/README.md`, `backend/.env.example`, `backend/pyproject.toml`,
  `backend/uv.lock`.
- `backend/app/core/config.py`, `core/errors.py`, `main.py`, `api/router.py`,
  `models/__init__.py`.
- `backend/app/tests/conftest.py`, `test_settings.py`, `test_migrations.py`,
  `backend/app/tests/integration/conftest.py`, `test_migrations.py`.

No frontend, inventory, purchasing, approval workflow, business formula, or existing
M1.1 migration was changed. The original M1.1 review report remains a historical record.

## Cross-team impact and TBD

Keerthi's M1.4 frontend should send JSON login requests, use bearer tokens, and consume
`/auth/me` for current roles/permissions. It must handle 401/403 separately and continue
to rely on backend checks. There is no OAuth2 password-form login endpoint.

The permission matrix, account provisioning, audited role/grant administration,
plant/resource scope and approval authority remain TBD. This milestone provides no
registration, password-change, or user/role/grant mutation endpoints. Future critical
configuration changes require the project's audit contract.

There are no refresh or server logout-revocation endpoints. A copied access token
remains valid until expiry unless the account is inactive; client logout discards
its token. Production HTTPS, login throttling, recovery/session policy and operator
provisioning must be agreed before deployment. None of these decisions grants KN
business authority through a role name.
