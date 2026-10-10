# M4.3 review handoff

Owner: Munees. Reviewer: Keerthi. Company: KNL.
Branch: `feature/munees/m4.3-reorder-timing`.
Base: `develop` at `885cb52` (merged M4.2, PR #15).

## Result

Read-only reorder timing combines M4.2's verified projection with explicitly
supplied MSL violation/availability policy and reusable supplier lead time. It
returns nullable reorder_required, current breach, expected crossing, order
deadline with inclusivity, earliest usable availability and an explanation.
Missing/stale evidence stays incomplete. No purchase quantity, buffer, business
defaults, order creation or operational policy authority is introduced.

## Review surface

- Pure engine: `app/domain/inventory_engine/reorder.py`.
- Typed request/response: `app/schemas/reorder.py`.
- Projection composition: `app/services/reorder.py`.
- Thin API: `app/modules/inventory/reorder_router.py`, registered in API router.
- Tests: `app/tests/test_reorder.py`, `app/tests/integration/test_reorder.py`.
- Contract: [M4.3](../docs/19_REORDER_TIMING_CONTRACT.md); backend and docs indexes updated.

New POST `/api/v1/inventory/reorder/assess` uses existing
`inventory.projection.read` and M4.2's repeatable-read database dependency. It has
no write side effects. No schema migration, table, permission seed, environment
setting or frontend change is required. Alembic head stays 0012_projected_inventory.

## Review decisions and limitations

Request approval references are supplied evidence, not independently verified KNL
approval. This assessment cannot install a policy or authorize an order. Operational
configuration ownership and verification remain TBD. Exact equality/availability
policy, supplier duration and calendars have no defaults. The calendar convention
is explicitly UTC with start excluded/end included; nonworking crossing deadlines
requiring intraday rules are undetermined. See the full contract for supported
semantics and output boundaries.

Keerthi should review nullable states and proposed M4.4 display integration. Existing
M4.2 final approval fields and source/reconciliation coverage still depend on the
upstream workflow and KNL mapping. No teammate-owned formula or workflow changes.

## Validation

Initial focused run: 44 tests passed with five existing deprecation warnings.
Final complete suite: **340 passed, 5 warnings in 44.49 seconds**, including
47 M4.3 engine/API cases and one new PostgreSQL composition case. PostgreSQL
integration tests were enabled. Existing migration round trips and metadata
comparison passed; Alembic reported "No new upgrade operations detected."
The five warnings are existing Starlette/AnyIO and Pydantic schema deprecations.
`git diff --check` passed. No frontend code changed, so frontend checks were not rerun.
The disposable test/preview schema check returned zero remaining schemas, and the
temporary PostgreSQL server was stopped. No application environment file or
production database was modified.

Changes are left uncommitted for owner review. Nothing is pushed or merged by this task.
