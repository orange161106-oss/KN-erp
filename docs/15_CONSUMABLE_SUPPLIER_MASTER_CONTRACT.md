# M2.3 consumable, unit and supplier master contract

Owner: Munees. Reviewer: Keerthi. Approved implementation plan: M2.3.
Branch: `feature/munees/m2.3-consumable-supplier-masters`.

## Schema and boundaries

`units`, `consumables`, `suppliers`, and `supplier_consumables` use UUID identifiers,
active flags, and UTC creation/update timestamps. Codes are trimmed, uppercased,
nonblank, and unique even after inactivation. Unit codes allow 16 characters;
consumable and supplier codes allow 64. Names allow 255 characters.
Consumables have an optional description and a required `unit_id` referencing
`units.id`. Supplier mappings have a unique `(supplier_id, consumable_id)` pair.
Foreign keys use RESTRICT. No delete API is provided.

No company data, default supplier, conversions, prices, stock quantities, MSQ,
lead times, MOQ, pack sizes, order multiples, or consumption rules are seeded.
The PRD/product `uom` contract is unchanged. Future requirement output may resolve
its `uom_id` from the consumable's `unit_id`; this milestone adds no calculations.

New consumables require an active unit. Creating/changing/reactivating a supplier
mapping requires an active supplier, consumable, and consumable unit. Inactivation
preserves existing mappings and identifiers; inactive parents prevent new use.
Units with active consumables cannot be deactivated until those consumables are
inactive. Reactivating a consumable requires an active unit. A consumable's unit
cannot change after any supplier mapping exists; a conversion/history policy is TBD.
Mappings retain their UUID when edited, with old/new associations recorded in audit.

## API and permissions

Resources are `/api/v1/masters/units`, `/consumables`, `/suppliers`, and
`/supplier-consumables` under the same masters prefix. Each provides:

- GET collection: `{items, total, limit, offset}`; `limit` 1–100 (default 25),
  `offset` >= 0, optional `q` (literal code/name search), and optional `is_active`.
  Omitting `is_active` includes both statuses. Mappings additionally support
  `supplier_id` and `consumable_id` filters.
- GET `/{id}`: includes inactive records for historical lookup.
- POST collection: create, returning 201.
- PATCH `/{id}`: edit explicitly supplied fields, returning 200.
- PATCH `/{id}/status`: `{is_active, change_reason}`, returning 200.

Create and edit requests also require a nonblank `change_reason` (max 1000).
Unknown fields and explicit nulls for required fields are rejected. Status changes
use the dedicated status API. An unchanged status is idempotent and creates no
duplicate audit event. No hard-delete endpoint is exposed.

Permission codes are `masters.<resource>.read` and `masters.<resource>.write`,
where resource is `units`, `consumables`, `suppliers`, or `supplier_consumables`.
Read covers list/detail; write covers create/edit/status. The migration registers
these eight technical codes with no role grants or users. No role-name bypass exists.
The company role matrix and audited account/permission provisioning remain TBD.

Errors follow `{code, message, details}`: 401 authentication, 403 permission,
404 unknown entity, 409 duplicates/inactive or conflicting references, 422 request
validation, and 503 unavailable database. Driver diagnostics and secrets are omitted.

## Audit and transactions

The shared `audit_logs` foundation stores UUID, actor FK (`users.id`, RESTRICT),
action, entity type/UUID, JSON old/new snapshots, reason, and UTC timestamp.
Snapshots contain only the master record's public fields. There are no audit
mutation APIs. Each actual master change and its audit entry commit together;
failed audit/persistence writes roll back the entire mutation. The service owns
commit/rollback. Row locks serialize master edits and active-reference decisions.
Retention/export and production database privileges remain deployment decisions.

## React integration

The mock persona selector is replaced by JSON login plus `/auth/me`. Access tokens
remain in memory; reload/logout clears them. API calls send Bearer credentials,
and 401 clears authentication. Master routes/buttons use backend permission codes;
backend checks remain authoritative. Existing unrelated role-based navigation
remains presentation only; no new grants are inferred from it.

Masters has unit, consumable and supplier pages. Supplier mappings are managed
within supplier details. Lists support search, pagination and active/all/inactive
filters. Forms show validation errors, require change reasons, and use active
references while retaining the selected existing reference when editing.
Vite proxies relative `/api` requests to local FastAPI, avoiding broad CORS changes.

## Migrations, validation and TBD

An additive merge revision joins the existing PRD and production-master heads;
the new master/audit migration follows it. Existing migration files are unchanged.
All existing models are registered for Alembic metadata discovery.
The existing PRD revision identifier exceeds Alembic's default VARCHAR(32).
The PostgreSQL Alembic environment creates VARCHAR(128) version columns and widens
older columns before running revisions. Offline SQL starting from an existing
revision emits the same widening. This changes only Alembic tracking metadata;
shared revision IDs and migration files are preserved.

Tests cover API permissions, uniqueness (including inactive records), references,
status rules, audit rollback/history, and PostgreSQL constraints/migration round trips.
Tests use isolated schemas only in an explicitly configured disposable `_test`
database. Frontend tests cover login/logout/401, forms, forbidden/read-only access,
and status/mapping behavior; build and lint are required.

Decimal-bearing fields are excluded until semantics, units, precision, range,
null/zero meanings, and rounding are approved. Unsupported quantity/constraint
fields are rejected now. Numeric Decimal validation remains TBD, not a completed
business-field test. Lead-time calendar rules, MSQ, preferred suppliers, supplier
contact fields, conversions and requirement-rule storage remain outside this change.
