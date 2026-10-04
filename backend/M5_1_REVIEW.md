# M5.1 review handoff

Owner: Munees. Reviewer: Yathish. Company: KNL.
Branch: `feature/munees/m5.1-purchase-recommendation`.
Base: clean `develop` at `ae06889` (M4.4 merged, PR #17).

## Implemented behavior

The purchase engine calculates target minus projected stock at receipt, applies
MOQ only to positive need, then selects the smallest quantity satisfying mandatory
pack and order increments together. It checks explicit maximums without capping
into an invalid quantity. Decimal/integer arithmetic retains four-place precision.

Munees authorized the proposed assumptions for implementation and later KNL
correction. They are versioned as M5.1_V1 with OWNER_APPROVED_PROVISIONAL labeling.
No numeric target, supplier value or calendar is invented. Known constraint states
need supplied references; unknown inputs return incomplete. The result and request
are explained alongside the authoritative M4.2 source projection.

## Files and API impact

- `app/domain/purchase_engine/recommendation.py`: pure quantity/constraint engine.
- `app/schemas/purchase_recommendation.py`: explicit states and output explanation.
- `app/repositories/purchase_recommendation.py`: supplier/material/unit context.
- `app/services/purchase_recommendation.py`: source, validity, timing and master checks.
- `app/modules/purchasing/recommendation_router.py` and shared API registration.
- `app/tests/test_purchase_recommendation.py` and integration counterpart.
- [Contract](../docs/20_PURCHASE_RECOMMENDATION_CONTRACT.md), setup/index and decision register.

New POST `/api/v1/purchasing/recommendations/assess` uses existing
`inventory.projection.read` and the repeatable-read session dependency. It does
not create a PO, persist an operational recommendation or modify stock. No table,
migration, permission seed, environment change or frontend change. Head stays
0013_inventory_alerts from merged M4.4. Existing alert/reorder/requirement behavior is untouched.

Shared migration tests are updated to expect the already-merged M4.4 head, alert
table and two additional permission codes. No applied migration is edited.
Validation also exposed duplicate index metadata in `app/models/alerts.py`:
`consumable_id` had both an explicit named index (already in migration 0013) and
an implicit `index=True` index absent from that migration. Removing the redundant
implicit declaration aligns metadata with the existing database; the explicit
index remains. No alert business logic or database objects change. Keerthi should
be aware of this one-line shared-schema compatibility correction.

## Review focus and remaining company inputs

Yathish should check simultaneous constraint semantics and the source-to-receipt
boundary. All amounts use stock units. Selected supplier/mapping must be active.
Raw 13 / MOQ 20 / pack 12 / multiple 10 yields 60. A maximum conflicting with 60
returns CONFLICT and null recommendation. A target below MSL is flagged rather
than replaced. Same-time receipt/demand/supply/MSL needs source event ordering.

Supplied approval references are not independent approval verification. Actual
company targets, constraints, calendars, golden examples and authoritative source
mapping remain operational inputs. Later KNL changes should update the versioned
contract/tests rather than silently reinterpret previous calculation evidence.
There is no durable recommendation/approval history in this read-only milestone.

## Validation

Initial focused engine/API run: **53 passed, 5 existing deprecation warnings in
9.38 seconds**. Final complete suite: **401 passed, 5 warnings in 65.00 seconds**,
with PostgreSQL integration enabled. M5.1 adds 56 engine/API cases and one PostgreSQL
case, including a concurrent supplier deactivation and repeatable-read verification.
Migration head, offline SQL, fresh upgrade, downgrade/re-upgrade and metadata checks
pass. Alembic reported "No new upgrade operations detected." The warnings are existing
Starlette/AnyIO and Pydantic deprecations. `git diff --check` passes. No frontend code
changed, so frontend checks were not rerun.
The disposable source-test/preview schema check returned zero remaining schemas;
the temporary PostgreSQL server was stopped. No application .env file or production
database was modified.

Changes remain uncommitted for review. This task does not push, merge or create POs.
