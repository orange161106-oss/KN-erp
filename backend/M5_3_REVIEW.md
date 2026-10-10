# M5.3 purchase orders — reviewer handoff

Owner: Munees. Reviewer: Keerthi. Company: KNL.
Branch: `feature/munees/m5.3-purchase-orders`.
Base: clean `develop` at `a0148c5` (M5.2 merged, PR #19).

## Result and operational boundary

Purchase order API/UI creates immutable drafts from positive reviewed demand,
reserves quantities transaction-safely and records issuance as a purchasing commitment.
No stock posting or consumption changes occur. Optional Decimal pricing requires
explicit approved terms; missing prices are unknown. Six new unassigned permission
codes separate reading, creation, pricing, issue, draft cancellation and submission.

Munees explicitly approved adding traced submissions and requiring legacy approvals
to be resubmitted. The new source API calculates M5.1 server-side, saves immutable
evidence, creates PENDING demand and uses the existing M5.2 review workflow. PO lines
retain the original report plus approval/material/supplier snapshots and references.

Important: no PO-linked fulfilment source exists yet. Issued pending quantity is
null/unknown, not fabricated. Partial/closed states and issued cancellation await
the GRN/fulfilment contract. Draft cancellation releases allocation. The pure pending
formula is covered by partial/full/unknown tests. This is a commitment foundation,
not a claim that operational receiving is complete.

## Changed files and migration/API impact

- PO domain/model/schema/repository/service/router modules; shared registration.
- `0015_purchase_orders` after `0014_purchase_approval`: purchase_orders,
  purchase_order_items, purchase_demand_evidence, protection triggers and six grants.
- New React PurchaseOrders screen, route, sidebar link and frontend tests.
- Backend API/domain and PostgreSQL concurrency/immutability tests; migration tests.
- [Contract](../docs/21_PURCHASE_ORDER_CONTRACT.md), backend setup and decision/index docs.

API prefix `/api/v1/purchase-orders`: demand submission, eligible sources, list,
detail, create, issue and cancel. No existing route is removed. New environment
variables: none. No users or business values seeded. No applied migration edited.

Shared compatibility correction: M5.2's ORM declared supplier/material indexes both
explicitly and implicitly, while migration 0014 has only the named indexes. Removing
the two redundant implicit declarations aligns metadata without changing actual
database indexes or approval behavior. Keerthi should review this small model change.

## Design points to review

- Separate SERIALIZABLE sessions; approval-row locks in consistent order; 409 retry
  responses; unique submission/creation keys and atomic audits.
- Drafts reserve approved quantity. Splits reuse M5.1's supplier increment checks.
  A whole MODIFIED quantity retains the reviewer's explicit override and reason.
- Source approval is rechecked at issue; terms/items/evidence are immutable.
- Technical PO number is UUID-based; company numbering remains a separate input.
- No guessed receipt fulfilment, pricing currency, rounding or approval limits.
- Currency-aware pricing is Decimal; frontend submits quantities/rates as strings.
- New permissions do not grant approval authority or send a PO to a supplier.

## Validation

Initial focused backend: 27 passed, five existing warnings. Initial full backend:
444 passed, five warnings in 202.14 seconds, including PostgreSQL migrations and
concurrency. Final validation after the split-constraint guard will be recorded below.
Initial frontend: 30 tests passed; TypeScript and production build passed. The final
frontend run also includes an explicit issue-action test. Changed-file lint passes.

Final validation: **445 backend tests passed, 5 existing deprecation warnings in
243.23 seconds**, with PostgreSQL integration enabled. This includes 28 M5.3
domain/API cases and 10 PostgreSQL cases for exact values, immutable history,
concurrent allocations/retries and cancellation release. Fresh migration,
downgrade/re-upgrade, offline SQL and metadata checks pass; Alembic reports no new
upgrade operations after applying head 0015.

Final frontend: **31 tests passed**. TypeScript compilation, production Vite build,
and lint on all changed TSX files pass. The machine's npm launcher references a
missing global npm-cli.js, so validation used the installed project tools directly
through Node. No dependency changes or global installations were needed.
`git diff --check` passes. No manual browser visual inspection was performed;
frontend validation consists of rendered-component tests and the production build.
Disposable source-test/preview schema cleanup found zero remaining schemas; the
temporary PostgreSQL server was stopped. No application environment file or
production database was modified.

No commit, push or merge is performed by this task. Review the unresolved fulfilment
boundary before treating this as a complete purchasing/receiving deployment.
