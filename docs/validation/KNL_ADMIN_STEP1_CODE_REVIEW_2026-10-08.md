# KNL Admin Step 1: code verification

Review date: 8 October 2026. Requested by Munees.
Reviewed commit: `4dee816`, including the preceding admin/authentication commits.
Conclusion: employee-account UI and storage are implemented, but the claimed
environment-controlled immutable Super Admin and granular authorization transition
are incomplete. This feature is not ready for production acceptance.

## Verified implementation

- `/admin` is connected to `UserManagement`.
- Full name, employee ID, ten feature flags, five plant flags and `is_super_admin`
  are present in the ORM and public user schemas.
- Employee ID has a database unique constraint. Public user responses exclude
  password hashes.
- Create/update request schemas reject extra fields. Creation checkboxes default
  to false. The frontend imports interface types with `import type`.
- UI includes employee details, password visibility, browser autocomplete hints
  and filtering of Super Admin rows.
- Both named migration files exist, with employee data following granular flags.
  Whether these migrations are applied on Supabase was not checked in this review.

## Findings requiring correction

### R01 — P1: feature flags do not control business permissions

`backend/app/services/auth.py:68` derives effective permissions solely from role
permissions. The feature flags are additional response properties.
`backend/app/security/permissions.py:14` authorizes only the effective permission
codes. Existing business screens and navigation also use legacy permissions/roles.
Frontend `CurrentUser` does not declare the fifteen new flags.

Isolated reproduction: master read with `can_view_master_data=false` and the old
read grant returned 200; the flag true without that grant returned 403. Unchecking
a capability therefore does not revoke access, and checking it does not grant it.

Correction: define one effective backend policy that gives the admin matrix its
documented meaning, then use it consistently in API and UI. Explicitly settle
whether role templates initialize grants or retain independent authority. Do not
silently combine an unchecked flag with an allowing role. Map PO creation, demand
approval, PO issue, pricing and receipt import to their distinct existing actions.

### R02 — P1: ordinary Admin can modify the Super Admin

`backend/app/modules/auth/user_router.py:19` permits both Super Admin and ordinary
ADMIN role users to manage accounts. `update_user` at line 139 does not reject
targets with `is_super_admin=true` before changing their password, status, roles
or flags. GET users also returns the account; the UI filtering is not an API lock.

Isolated reproduction: an ordinary ADMIN identity successfully disabled a Super
Admin through PUT (200). The account was also included in GET users.

Correction: enforce the intended operator policy at the backend and guard protected
targets before every mutation. Protect identity/provisioning through an explicit
contract. There is no user DELETE endpoint to verify, so this review does not claim
a deletion exploit.

### R03 — P1: environment provisioning and singleton protection are absent

`backend/app/core/config.py:48` defines Super Admin settings with built-in defaults,
including a password. Startup in `backend/app/main.py` does not consume these
settings to provision or reconcile an account. No startup provisioning call was
found. The dev seeder instead uses a hard-coded admin identity/password and marks
that account as Super Admin; it still grants every permission to every role.
The model/migrations do not constrain the database to one Super Admin.

Correction: remove built-in bootstrap credentials, implement explicit controlled
provisioning and uniqueness/concurrency protection, and keep development seeding
from changing production accounts. Define credential rotation without resetting
the account unexpectedly on each server start. Do not print passwords.

### R04 — P1: plant flags are separate from actual plant authorization

`backend/app/services/plant_workflow.py:45` obtains access from `user_plants`.
Account creation/update neither synchronizes that relation nor switches the
authorization helper to the new flags. Fixed-number flags also need a stable
mapping to actual Plant IDs. Hiding checkboxes by a role label does not enforce scope.

Isolated reproduction: a true Plant I flag without a legacy assignment returned
403 from the access helper. With the flag false and an assignment present, the
helper allowed the action.

Correction: select one authoritative plant assignment model, reflect it in the
matrix and enforce it for both list/read and mutation operations. Preserve already
approved assignments during migration and test cross-plant denial.

### R05 — P1: authentication-only workspace routes allow ungranted mutations

`backend/app/modules/prd/prd_workspace_router.py` checks `get_current_user` but
does not require an action grant. The requirement workspace follows the same
pattern. This predates Step 1 but blocks accepting the promised permission matrix.

Isolated reproduction: an identity with no roles, no permission codes and planning/
calculation flags false successfully saved a PRD workspace row (200).

Correction: protect each read/import/create/update/delete/export/calculation action
through the same effective permission service. Add negative API tests; UI controls
are insufficient.

### R06 — P1: account and permission changes are not audited

User create/update routes commit mutations directly without an audit record,
actor/reason or an auditable old/new policy snapshot. Both create and update routes
currently omit the application service layer used for other critical mutations.

Isolated reproduction: disabling the protected target, clearing an employee ID
attempt and resetting a password produced zero additional AuditLog records.

Correction: place administration mutations in a transactional service and audit
create, status, identity and access changes. Record password-change occurrence,
never plaintext or password hashes.

### R07 — P1: password reset skips creation validation

`backend/app/schemas/user.py:46` permits any SecretStr length on update, while
creation has explicit length limits. Isolated PUT with a one-character password
succeeded (200).

Correction: share password bounds across create/reset and define omitted, null and
empty behavior consistently. Continue excluding credentials from errors and logs.

### R08 — P2: clearing optional employee fields is silently ignored

The frontend sends null when clearing full name/employee ID. The backend only
assigns these fields when their value is not None. Isolated clearing of an employee
ID returned 200 but retained the original value.

Correction: use Pydantic's fields-set tracking to distinguish an omitted field
from an explicit clear. Normalize/bound employee values and handle uniqueness races
as useful validation conflicts rather than unexpected 500 responses.

### R09 — P2: account state and existing roles are not preserved by the form

The create form shows an Account Active checkbox but omits `is_active` from its
creation payload; the backend always creates active accounts. Editing always sends
one selected role, so an unrelated edit can remove a user's other roles. APPROVER
is missing from the base-role dropdown. Non-PLANT_INCHARGE saves force all plant
flags false regardless of other selected capabilities.

Correction: make the UI match the approved role/template contract, preserve
unrelated grants, support required reviewer categories, and either implement
creation status or remove the ineffective control.

### R10 — P2: autogenerated migration includes unrelated index removal

The granular-flags migration drops `ix_goods_receipt_records_is_deleted` and
`ix_prd_records_is_deleted`, unrelated to adding permissions. Confirm intentional
schema/index ownership and query-performance impact. If already applied, use a
follow-up migration for corrections rather than rewriting migration history.

## Corrections to the supplied completion summary

- Flags are exposed through database-backed CurrentUser and `/auth/me`, not stored
  in JWT claims. Tokens retain identity/security metadata. Loading current grants
  on each request supports immediate revocation when enforcement is integrated.
- Super Admin settings exist, but environmental provisioning/locking is not wired.
- Filtering a row from the UI does not make the account immutable or undiscoverable.
- The form configures a fixed set of capability columns; this is not yet a complete
  dynamic permission engine. New capability columns still require code/schema work.
- Migration files were inspected; hosted application status was not independently
  verified. No remote migration was executed.

## Actual verification and limits

- Executed ten targeted observations using an in-memory SQLite database, synthetic
  accounts and FastAPI dependency overrides. No deployed account, credential or
  source data was used. Startup/lifespan was intentionally bypassed to avoid opening
  a configured remote connection. Observations demonstrate route/policy defects,
  not the deployed database's current user assignments.
- Results: master flag false + old grant = 200; flag true + no old grant = 403;
  ungranted PRD workspace write = 200; Super Admin included in API list; ordinary
  Admin can disable it; employee-ID clear ignored; one-character reset accepted;
  user-update audit count 0; plant flag true without assignment = 403; plant flag
  false with existing assignment = allowed.
- TypeScript `tsc -b` passed.
- No new administration regression tests were found in the existing suites.
- PostgreSQL singleton/concurrency/migration checks, browser end-to-end behavior
  and deployed Supabase migration state remain unverified.
- Application source and operational data were not changed. This review document
  was added; the isolated probe is under ignored `backend/.cache`.

## Recommended next work

Keep the employee UI/storage. Complete protected bootstrap, target immutability,
effective permissions, plant scope, validated audited administration and meaningful
allow/deny tests before approving Step 1 for production. These technical corrections
can proceed independently of Munees's eight pending KNL workflow answers.
