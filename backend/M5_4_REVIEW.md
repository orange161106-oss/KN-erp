# M5.4 imported GRNs — reviewer handoff

Owner: Munees. Reviewer: Keerthi. Company: KNL.
Branch: `feature/munees/m5.4-grn-inventory`.
Base: clean develop at `b2ca5f2` (M5.3 merged, PR #20).

## Outcome and confirmed decisions

Munees explicitly confirmed existing-ERP posting/stock ownership and accepted-only
PO fulfilment. The new API/UI imports posted source receipts with matching usable
receipt events and authoritative snapshots. Rejected material stays pending for
replacement. Import, receipt links, stock evidence and audits commit together.

The PO response derives physical received, accepted, rejected, pending and receipt
status from immutable GRN lines. Commitment status remains DRAFT/ISSUED/CANCELLED;
the separate fulfilment_status reports NOT_APPLICABLE/NOT_RECEIVED/PARTIAL/COMPLETE.
This avoids mutable status/counter drift and leaves issued cancellation/closure rules
unimplemented until approved. Imported figures are explicitly non-live.

## Migration and API impact

- Migration `0016_grn_imports` follows `0015_purchase_orders`. It adds grns/grn_items,
  restricted foreign keys, exact NUMERIC quantities, source uniqueness, stock links
  and PostgreSQL append-only triggers. No applied migration is edited.
- Two new permissions: purchase.grns.read and purchase.grns.import, without grants.
  Import additionally requires inventory.stock.import and existing import-enabled
  configuration. No new environment variables or users/business values are seeded.
- New POST `/api/v1/grns/imports`, GET `/api/v1/grns` and GET `/api/v1/grns/{id}`.
  React `/grns` provides export preview, import and history/detail.
- Existing PO APIs now return numeric issued pending on an imported-data basis,
  rather than null. pending_basis becomes IMPORTED_ACCEPTED_GRNS, with added quantity,
  fulfilment_status and fulfilment_is_live fields. Frontend and tests are coordinated.

## Review points

- SERIALIZABLE receipt sessions, a PO parent lock before reading totals, followed by
  deterministic consumable locks. A retry after conflict rechecks outstanding quantity.
- Same stable ERP document key and content replays; changed content conflicts.
  One source stock event cannot fulfil two GRN lines/documents.
- The stock service now exposes a flush-only staging primitive; its existing public
  import wrapper retains commit/rollback ownership. GRN imports own the outer commit.
- Balance remains the latest ERP snapshot, never snapshot plus receipts. Existing
  stock source records can be reused without duplicates. Older snapshots do not
  regress balances; failed imports preserve all previously committed history.
- Source PO/supplier/item/material/unit/time/quantity evidence is validated. Missing
  snapshots, unresolved inspection, extra stock events and inexact quantities fail.
- Excess physical receipts are held as policy-TBD without writes. Rejected quantities
  can be replaced later without double-fulfilling the PO.
- Changed source snapshots still require projection reconciliation through M4.2;
  no automatic duplicate incoming or pending-PO subtraction is introduced.

## Validation

Initial focused backend: 83 passed, five existing warnings. Initial complete backend:
472 passed, five existing deprecation warnings in 166.56 seconds, with PostgreSQL
integration enabled. This includes migration fresh upgrade, downgrade/re-upgrade,
metadata comparison, source immutability, simultaneous duplicates/excess receipts
and rollback after stock/GRN flush.

Final frontend: 37 tests passed; TypeScript, Vite production build and changed-file
ESLint passed. UI tests cover permission denial, read-only/empty/loading/error states,
exact decimal preview, unchanged retry payload and duplicate replay feedback. No
manual visual browser inspection or live KNL ERP integration was performed.

A selected-file backend rerun exposed fixture-discovery ordering when
mixing unit and integration modules (61 passed, 11 fixture-setup errors). The standard
whole-suite entry point completed final validation successfully: **475 passed,
5 existing warnings in 171.60 seconds**, with PostgreSQL integration enabled. This
includes 21 new GRN schema/API tests and 9 PostgreSQL GRN tests, including the final
response presentation and valid concurrent partial-receipt retry. Use the standard
`pytest app/tests` entry point with the dedicated TEST_DATABASE_URL for review.

Fresh migration, downgrade/re-upgrade, offline SQL and metadata checks pass at head
`0016_grn_imports`; Alembic reports no unexpected upgrade operations. Git whitespace
checks pass. No application database or real KNL receipt data was used for validation.

## Operational limits and handoff

Real source export mapping/API, source-to-local PO-item identity, usable snapshot
semantics and complete receipt coverage must be verified before enabling imports.
Over-receipt policy, corrections/reversals, unresolved inspection and issued
cancellation remain TBD. Numeric examples are synthetic, not company golden data.
This is a tested import foundation, not a claim of live production integration.

See [contract](../docs/22_GRN_INVENTORY_CONTRACT.md) and the backend README for payload,
permissions and setup. Work is for review; no merge or deployment is performed.
