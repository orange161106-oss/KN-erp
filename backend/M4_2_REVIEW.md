# M4.2 review handoff — KNL MSL and projected inventory

Owner: Munees. Reviewer: Yathish. Prepared: 2026-10-04.
Branch: `feature/munees/m4.2-projected-inventory`.
Base: develop `acaf02a`, containing merged M4.1.
Status: local implementation for review; no commit, push, PR, merge or deployment.

## Result

The deterministic backend engine computes a selected planning version's projected
central stock from an identified usable snapshot, outstanding confirmed receipts
and reconciled remaining demand. It preserves four decimal places and negative
shortages, reports current/projected MSL conditions separately, records the first
supported future breach, and explains each included/excluded source input.

MSL history and lead-time intervals are supplied as approved source evidence.
Lead-time availability is never treated as a receipt by itself. Fulfilled demand,
reserved demand already excluded from usable stock, received supply and cancelled
supply are accounted for once. Duplicate source identities are rejected. A later
receipt does not erase an earlier breach; mixed events sharing a timestamp require
source ordering instead of assumed receipt-first processing.

The existing final-requirement handoff contains monthly totals rather than a dated
schedule. Without approved timing/reconciliation/supply evidence, the API returns
INCOMPLETE with monthly totals and named limitations, null projected stock and no
claimed breach date. Known current MSL can still be reported when demand timing is
missing. Stock arithmetic may complete without MSL/lead time, with the related
assessment explicitly unavailable. No demand spreading, safety buffer, purchase
quantity or MSL approach/equality alert policy has been invented.

## Migration, APIs and files

Revision `0012_projected_inventory` follows `0011_central_inventory`; existing
applied revisions are untouched. It adds `projection_input_sets`, storing immutable
source JSON, requirement fingerprint/manifest, material/version/snapshot references
and importer/time. Import and audit commit atomically. PostgreSQL UPDATE/DELETE
protection reuses M4.1's function. Downgrade drops this evidence and its new permission codes;
assigned role grants must be removed first. Test downgrade only in disposable databases.

New unassigned permissions: `inventory.projection.read` and
`inventory.projection.import`. These explicitly cover central planning across plants;
no role inherits them automatically. `PROJECTION_IMPORT_ENABLED` defaults to false.
The environment example still contains blank names only.

| Endpoint | Result |
| --- | --- |
| GET `/api/v1/inventory/projections/status` | Source/timing capability and import setting |
| GET `/api/v1/inventory/projections` | Projection/explanation or explicit incomplete result |
| POST `/api/v1/inventory/projections/inputs` | Audited evidence import; 201 new, 200 identical replay, 409 conflicting identity |

The GET takes material/version UUIDs, an aware exclusive cutoff and optional source
set identity. A request without a source set returns the current snapshot identity,
monthly plant totals and limitations; those references support subsequent verified
source mapping. Response includes M4.2_V1 engine/schema identity and selected-version
scope. No operational calculation is presented as a live stock feed.

New files are the projection domain engine, schema, model, repository, service,
thin inventory router, migration and unit/integration tests. Shared API/model
registration, setting/example, migration tests, backend README and decision/index
docs are updated. Full behavior is in
[the projection contract](../docs/18_PROJECTED_INVENTORY_CONTRACT.md).
M4.4 can consume these APIs for planning/alert screens; no frontend changes are
part of this backend milestone.

## Cross-team boundaries and operational dependencies

M4.2 reads M3.5's final-requirement service and records its calculation/adjustment
source identities, including approval evidence. It does not change Yathish's
formulas, Keerthi's workflow, M4.1 stock semantics or supplier master fields.
Existing planning-version approved_at/approved_by fields are prerequisites; absent
evidence and draft/superseded versions produce FINAL_REQUIREMENT_NOT_APPROVED.
M4.2 does not populate approval fields or infer authority from role labels. The
upstream final-release contract needs Yathish/Keerthi verification for operational use.

Projection reads/import validation use a PostgreSQL REPEATABLE READ transaction
separate from authentication, so quantities, source identities and approval evidence
come from one consistent view. Requirement changes or a newer stock snapshot make
older source sets incomplete until a new reconciliation is supplied. Reports return
the retained inputs; old evidence is not silently overwritten or rebased.

Before enabling operational imports, KNL must supply/verify: real demand timing;
selected-version coverage including other obligations within the horizon;
fulfilled/reserved reconciliation against net usable stock; confirmed incoming
schedule identities/statuses/partial receipts/cancellations and usable dates; MSL
values/effective dates; lead-time start/availability intervals and calendar evidence;
named central read/import grants. Exact approach/equality alert policies remain TBD.

No company values, accounts, source connector, supplier defaults or safety buffer
are seeded. All test quantities/approvals/calendars are synthetic and do not establish
KNL policy. Changes remain review-ready foundation code with imports disabled.

## Validation

Focused M4.2 engine/API validation: **45 passed**, with five existing framework/schema
deprecation warnings. It covers no incoming, receipt before/after breach, equality,
future breach/recovery, effective MSL changes, Decimal precision, duplicate identities,
partial received/cancelled supply, fulfilled/reserved demand, unknown/overdue timing,
coverage limits, lead-time mapping, source changes, permissions and audit rollback.

Five new PostgreSQL cases cover exact API serialization/evidence, UPDATE/DELETE
protection, concurrent import uniqueness/audit and a report while requirements are
changed concurrently. Migration checks include fresh upgrade, single head, metadata
comparison and downgrade/re-upgrade.

Final validation on Python 3.12.14 / PostgreSQL 17.11: **292 passed, 5 warnings in
120.97s**, with all PostgreSQL integration tests enabled. The warnings are existing
Starlette/AnyIO and production-schema Pydantic deprecations. Alembic reported no new
upgrade operations after applying the migration. Changed Python modules parse with
no duplicate top-level definitions; `git diff --check` passes. No frontend code
changed, so frontend checks were not rerun for this backend-only milestone.

The temporary PostgreSQL validation server was stopped after testing. The disposable
test/preview schema cleanup check returned zero remaining schemas. No application
.env file or production data was modified.
