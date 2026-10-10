# M1.3 authentication and RBAC contract

Owner: Munees. Reviewer: Keerthi. Approved implementation plan: M1.3.
Branch: `feature/munees/m1.3-auth-rbac-backend`.

## Schema

The authentication foundation adds `users`, `roles`, `permissions`, `user_roles`
and `role_permissions` after `0001_backend_foundation`. Entity identifiers are UUIDs.

- Users have a normalized, unique username, password hash, active flag and UTC
  creation/update timestamps. Normalization strips surrounding username whitespace
  and case-folds it. Passwords are never stripped, normalized or truncated.
- Roles have a unique code and display name. Permission records have a unique code
  and description. Association tables use foreign keys and unique pairs.
- The migration seeds ADMIN, PLANNER, PLANT_INCHARGE, STORE, PURCHASE, APPROVER and
  MANAGEMENT as categories only. It seeds no permissions, grants or user accounts.
- An ADMIN role is subject to the same explicit permission grants as every other role.
- Approved configuration defines permission codes and role/user assignments. There
  is no built-in KNL approval matrix, monetary limit or plant-access policy.

## API

`POST /api/v1/auth/login` accepts JSON:

```json
{"username": "<username>", "password": "<password>"}
```

Success is HTTP 200 with `access_token`, `token_type` (`bearer`) and `expires_in`
(seconds). Responses include `Cache-Control: no-store` and `Pragma: no-cache`.
Invalid credentials, unknown users and inactive users share HTTP 401,
`INVALID_CREDENTIALS`, and the same generic message.

`GET /api/v1/auth/me` accepts `Authorization: Bearer <access_token>` and returns
`id`, `username`, `roles` (sorted role codes) and `permissions` (sorted effective
permission codes). No user API response contains a password hash.

Missing/invalid/expired bearer tokens or inactive/missing users yield HTTP 401,
`NOT_AUTHENTICATED`, with `WWW-Authenticate: Bearer`. Authenticated users missing a
required permission yield HTTP 403, `PERMISSION_DENIED`. Errors follow the existing
`code`, `message`, `details` format; submitted credentials are omitted from validation
errors. Request validation failures are HTTP 422. Database failures are HTTP 503,
`DATABASE_UNAVAILABLE`, never an authorization allow result.

## Backend checks

`get_current_user` verifies the access token and loads the active user plus current
role/permission assignments from PostgreSQL on every authenticated request.
`require_permissions(*codes)` requires all specified permission codes. Empty required
sets are rejected as a programmer configuration error; authentication-only routes
use `get_current_user` explicitly. Unknown or ungranted permissions deny access.

Routes declare dependencies; services and centralized checks implement policy.
Role names or browser-provided claims never grant access. Test-only protected routes
exercise this contract without introducing production business endpoints.

## Passwords, access tokens and settings

- Hash passwords with Argon2id via `pwdlib[argon2]`. Verify a dummy hash for unknown
  accounts; never log credentials, hashes or tokens. This is mitigation for obvious
  timing differences, not a guarantee of constant request timing.
- Sign JWT access tokens using HS256 with an operator-generated secret of at least
  32 UTF-8 bytes. There is no default signing secret. Algorithm selection is fixed
  server-side and never taken from the received token.
- Tokens contain only user identity and security metadata: `sub`, `iat`, `exp`,
  `iss`, `aud`, and `token_type=access`. They contain no passwords or permission grants.
- Require and validate signature, expiry, issued-at time, issuer, audience, token
  type and a UUID subject. The default lifetime is 15 minutes, configurable from
  1 through 60 minutes.
- Add `AUTH_SECRET_KEY`, `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES`, `AUTH_TOKEN_ISSUER`
  and `AUTH_TOKEN_AUDIENCE` to settings. Example environment entries remain blank.
- Credentials/signing secrets belong only in ignored local environment files or
  the deployment secret store. A signing key is required for application startup;
  Alembic schema-only operations do not require one.

The JSON login endpoint uses HTTP bearer authentication, not an OAuth2 password-form
endpoint. Keerthi's frontend can log in with JSON and use `/auth/me` as the source of
navigation permissions. Backend authorization remains mandatory.

## Configuration and limits

Initial account provisioning and audited user/role/permission administration remain
TBD. This milestone exposes no public registration or user/role/grant mutation API.
Test fixtures provision synthetic accounts only in isolated transactions. Future
administration changes must record actor, action, entity, old/new state, reason and
UTC timestamp under the project audit rules.

Plant/resource scope, approval authority, limits and KNL permission matrix remain TBD.
Generic permission checks do not imply access to a plant or business resource.
Protected business APIs must add approved resource-scope checks when introduced.

There is no refresh-token or logout-revocation endpoint in M1.3. Client logout discards
the token; a copied token remains valid until expiry unless the user is inactive.
Permission removal and user deactivation take effect on the next authenticated
request. Production HTTPS, login throttling, account recovery and session requirements
must be agreed before deployment.
