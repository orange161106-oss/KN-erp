# M4.1 review handoff — KNL central inventory foundation

Owner: Munees. Reviewer: Keerthi. Prepared: 2026-10-04.
Branch: `feature/munees/m4.1-central-inventory`, based on develop `39170c4`.
Status: local, uncommitted review draft. No deployment, push, PR or merge performed.

## Result and KNL boundary

KNL's supplied `INV_KN_Discussion_Answers_Updated.pdf` assigns opening/cutover,
reservations, warehouse approvals, issue/return documents, corrections and MSL
authority to the existing ERP. Munees authorized continuing M4.1 with these answers
and confirmed the company name KNL. The source PDF is preserved; its SHA-256 is
`CAB580B5599B0B3FAFEF9B770C9F95BC11D7845F37F8659693817F3A9D6B0FE7`.
It supplies business decisions, not instructions to execute tools or deploy.

This foundation imports immutable, already-posted movement history and authoritative
usable balance snapshots. It provides a normalized source contract, not a live ERP
connector. Three movement types are accepted: usable accepted RECEIPT (+), dispatch
ISSUE (-), usable plant RETURN (+). Damaged/rejected/pending and PO ordered quantity
are excluded. No plant-store, opening, adjustment, reservation or warehouse approval
workflow was added. Issue is not automatically actual consumption.

Latest source `as_of` determines reported stock. Partial history is never summed
into a fabricated opening/balance or added again to a reported snapshot. Missing
balance is null/NOT_IMPORTED; reports include source and import times plus
`is_live=false`. Source must explicitly attest nonusable/reserved exclusions.
Quantities use exact Decimal/NUMERIC(18,4). Different units require a supplied
approved factor/reference; inexact four-place results are rejected without rounding.

Imports lock materials in UUID order, detect immutable source-key conflicts,
commit batch/movements/snapshots/audit atomically and safely replay identical exports.
PostgreSQL triggers reject direct UPDATE/DELETE on the new tables. Consumable unit
changes are blocked once stock records exist. Standard backend permission checks
apply; no ADMIN bypass and no production grants/accounts/data are seeded.

## Migration and API impact

One Alembic head: `0011_central_inventory`, parent `0010_requirement_approval`.
New tables: `stock_import_batches`, `stock_transactions`, `stock_snapshots`.
New unassigned permission codes: `inventory.stock.read`, `inventory.stock.import`.
Setting `INVENTORY_IMPORT_ENABLED` defaults to false; `.env.example` remains names
with blank values only. No credentials or local environment files are committed.
Downgrade drops stock history and requires assigned permission grants to be removed;
test round trips ran exclusively in disposable schemas.

Under `/api/v1/inventory`:

| Method/path | Behavior |
| --- | --- |
| GET `/status` | Typed source boundary/import capability |
| GET `/balances` | Paginated code/name and active-status filtered stock reports |
| GET `/balances/{consumable_id}` | Material's latest reported usable stock |
| GET `/transactions` | Paginated material/movement/aware-time source history |
| POST `/imports` | Permission/configuration gated normalized import; 201 new, 200 replay |

There are no warehouse mutation/edit/delete APIs. React `/inventory` replaces the
placeholder, uses explicit read permission for navigation, shows dated reports and
history, and exposes import only to technical importers while enabled. Import
success/replay feedback survives data refresh. KNL display/documentation naming is
corrected; database/package/file identifiers and existing JWT claims remain compatible.

## Actual validation

Environment: Python 3.12.14, PostgreSQL 17.11 on an isolated local test server,
Node 25.8.0, locked project dependencies. Results on 2026-10-04:

| Check | Actual result |
| --- | --- |
| Full backend suite, including configured PostgreSQL integration | **242 passed**, 5 existing deprecation warnings, 41.80s |
| Frontend Vitest | **24 passed** (2 files), 6.65s |
| TypeScript + production Vite build | Passed |
| ESLint on changed React/test files | Passed, no warnings |
| Full repository frontend ESLint | Failed: **5 existing errors, 2 existing warnings**, listed below |
| PostgreSQL fresh upgrade/head + Alembic schema check + downgrade/re-upgrade | Passed; no new upgrade operations detected |
| New real PostgreSQL inventory tests | 12 cases included in the full suite |
| Offline migration/head-chain tests | Passed in the full suite |
| Browser with real API/PostgreSQL synthetic data | Login, KNL title/navigation, 100.1234 balance, missing report, source conversion, ISSUE filter and duplicate import replay verified |

New tests cover Decimal limits/exact conversion, four-place serialization, UTC,
unsupported/uncertain source states, exclusion attestations, missing references,
permission allow/deny, default-disabled imports, source identity/time conflicts,
rollback on audit/conversion failure, latest-source balance selection, absence of
local warehouse mutations, unit-change protection, SQL immutability and concurrent
identical/reused/conflicting source imports. Test users/grants/factors are synthetic,
not KNL policy or production records.

Full frontend lint failures are in unchanged files:

- `src/features/plant_workflow/PlantWorkflow.tsx`: 3 set-state-in-effect errors.
- `src/features/rules/types.ts`: 2 explicit-any errors.
- `src/features/mappings/ProductionMappings.tsx` and
  `src/features/rules/ConsumptionNorms.tsx`: 2 dependency warnings.

These are recorded without weakening lint rules or changing teammate workflow/rules
behavior. The full repository lint gate needs its owners' fixes before merge.

## Shared migration fixes exposed by validation

Fresh PostgreSQL migration initially failed at existing M3.4/M3.5 permission seeds:
SQL UUID expressions were sent as scalar Psycopg parameters. The shared Alembic
PostgreSQL implementation now compiles those expression-valued inserts online.
Offline handling stays intact; no applied migration file was edited.

`alembic check` also exposed existing model/migration drift. Mapping unique names
now match migration 0006 using SQLAlchemy's convention marker (including PostgreSQL
long-name truncation). Ten `index=True` declarations absent from migration 0008
were removed from requirement metadata; its existing composite indexes remain.
This restores the published schema contract without changing database tables,
requirement formulas, calculation outputs or plant approval logic. Review this
mechanical metadata alignment with Yathish/Keerthi; no cross-domain business change.

## Files and remaining operational decisions

Implementation is split between inventory domain helpers, models, schemas,
repository, service, thin module router, revision 0011 and unit/integration tests.
Shared configuration/API/model registration, master unit-history guard and migration
tests are updated. React types/view/tests and KNL labels are added/updated.
Contracts are [central inventory](../docs/17_CENTRAL_INVENTORY_CONTRACT.md) and
[business decision register](../docs/16_KN_BUSINESS_DECISION_REGISTER.md).
Backend/frontend READMEs document configuration, endpoints and normalized input.

Before operational imports: provide a real ERP stock export/API, verify usable-stock
field and exclusion evidence, source/master unit mapping, snapshot identities and
approved conversion values, configure named technical read/import access and refresh
policy. Named approver/effective-date/evidence details in the PDF remain TBD.
MSL approach threshold/material values belong to subsequent M4.2/M4.4 decisions;
the 500/1,000 example is not a default or defined alert rule.

This is review-ready foundation code, not an enabled production inventory feed.
No purchase recommendations, business defaults, plant balances or automatic MSL
approvals are introduced.

Cleanup verified: zero M4.1 test/preview schemas remain. Preview API/frontend and
the temporary PostgreSQL validation server are stopped. Application database data
and local credentials were not changed. The original PDF was not modified.
