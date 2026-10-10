# M2.3 review handoff

Owner: Munees. Reviewer: Keerthi (`keerthivasn` on GitHub).
Branch: `feature/munees/m2.3-consumable-supplier-masters`, based on local develop
`6e7cf59`. Implementation is review-ready; no merge was performed.

## Result

Units, consumables, suppliers and supplier/consumable mappings have protected
create/read/edit/inactivate/reactivate APIs and React screens. Codes stay unique
after inactivation. Supplier mappings and history remain stored. Shared audit entries
commit atomically with actual changes; failed writes roll back. Real login/current-user
integration replaces the mock role selector. Master access uses explicit backend
permission grants, including for ADMIN. Access tokens remain in memory.

There are no purchase calculations, stock balances, company seeds, default suppliers,
MSQ interpretations, numeric supplier constraints, or requirement-rule duplicates.

## Migration and API impact

- `0004_merge_master_heads` joins `0003_product_customer_prd_staging` and
  `acfaead772de`. Existing applied migration files are unchanged.
- `0005_inventory_masters` adds `units`, `consumables`, `suppliers`,
  `supplier_consumables`, and `audit_logs`; registers eight permission codes with
  no grants/users/company records.
- Alembic PostgreSQL version tracking uses VARCHAR(128), including widening older
  columns, because the existing PRD revision ID exceeds the default VARCHAR(32).
  Offline upgrades from existing revisions include the widening statement.
- Existing ORM metadata is fully registered. Product/customer indexes now match
  their existing migrations; no product/customer data columns were changed.
- Four resources under `/api/v1/masters` support GET list/detail, POST, PATCH edit,
  and PATCH `/{id}/status`. Lists return `{items,total,limit,offset}`. All mutations
  require a nonblank reason. No DELETE endpoints exist.
- Existing product/customer and PRD routers were unregistered and returned 404;
  shared registration restores their existing contracts. Their domain logic and
  existing authorization policies are unchanged.

## Actual validation — 2026-10-01

Complete backend suite, run from `backend/` with an explicitly configured isolated
test PostgreSQL database:

```text
python -m pytest -p no:cacheprovider --basetemp=<dedicated test temp directory> --tb=short -x
139 passed, 5 warnings in 25.02s
```

This includes 25 PostgreSQL integration cases and 114 unit/API cases. It covers
auth regressions, PRD regressions, uniqueness, reference constraints, permissions,
inactive history, mapping updates, audit snapshots/rollback, UTC timestamps, migration
round trips, and widening an existing 32-character version column.

Real PostgreSQL migration output, repeated after round trips:

```text
0005_inventory_masters (head)
No new upgrade operations detected.
```

Frontend final checks:

```text
npm test             15 passed (15), duration 7.30s
npm run build        TypeScript check and Vite production build succeeded
npm run lint         exit 0
```

Browser verification used synthetic accounts/data in a separately named disposable
schema: real login, unit create/edit/deactivate/reactivate, active/inactive filtering,
consumable unit-name lookup, and supplier mapping display succeeded. A status-select
accessible-name issue found in real-browser verification was corrected and covered
by an added frontend test. Logout/current-user/401/403 behavior also has component tests.

The five warnings are existing Starlette/AnyIO and production-schema Pydantic
deprecations. No failing test was skipped or changed to xfail. Unsupported Decimal
constraint fields are tested as rejected; numeric business-field validation remains
TBD until a numeric field's semantics are approved.

## Files and cross-team impact

- Backend: inventory master models/schemas/repository/service/router, audit model,
  model registration, shared router registration, Alembic environment/two revisions,
  master API/PostgreSQL tests, updated migration assertions, dependency manifest/lock,
  README and this handoff.
- Frontend: authenticated API client (including existing multipart support), real
  Login/AuthProvider, App/sidebar integration, master feature components, Vite local
  API proxy, Vitest/Testing Library tests/configuration, package manifest/lock and README.
- Documentation: `docs/15_CONSUMABLE_SUPPLIER_MASTER_CONTRACT.md`, documentation index,
  plus ignored local validation artifacts. Environment examples contain no real values.
- PRD integration fixes were necessary for pre-existing regression/build failures:
  declared missing import packages, restored router registration, and corrected only
  frontend typing/effect issues. Requirement formulas and PRD business behavior were
  not rewritten.
- Keerthi reviews the shared login/navigation and audit contract. Yathish can consume
  stable consumable/unit UUIDs in M2.4; product/PRD unit fields and rule storage are
  unchanged. No messages were sent to teammates.

## Remaining decisions and deployment prerequisites

Role grants and ERP account provisioning remain TBD/configuration. A migrated database
has no default ERP user; the eight master permission records are unassigned. The role
matrix must be approved and provisioned before real operators can use these screens.
Database credentials are separate from ERP logins.

Lead-time definition, calendar/business days, MOQ, pack size, order multiple, units,
precision, null/zero meanings, MSQ, supplier contacts/preference, conversions and unit
reassignment/history rules remain excluded pending approval. Production HTTPS,
account recovery, login throttling, backup/restore and runtime/migration privileges
are existing deployment prerequisites, not completed by this master-data milestone.

The user's regular PostgreSQL installation and `backend/.env` were not changed.
Validation used only the dedicated test database and temporary schemas. On resuming
2026-10-02, the temporary PostgreSQL and M2.3 preview processes were no longer running.
Windows Code Integrity now blocks the validation runtime's `libpq.dll`. Removal of
the disposable browser schema could not be confirmed; synthetic preview data may
remain in the ignored, stopped test cluster. No Windows security policy was changed.
