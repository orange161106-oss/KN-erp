# M5.4 imported GRNs and inventory integration

Owner: Munees. Reviewer: Keerthi. Company: KNL.
Branch: `feature/munees/m5.4-grn-inventory`.

## Confirmed authority and quantity meaning

On 2026-10-05 Munees explicitly confirmed both decisions:

- Existing ERP posts GRNs and owns central stock; this app imports posted GRNs.
- Only accepted usable quantity fulfils the PO. Rejected quantity remains pending
  for replacement.

This preserves the M4.1 authority boundary. There is no local warehouse posting,
inspection approval, reservation adjustment or balance editing. Each normalized
source receipt must reference an issued local PO and its exact supplier, line,
consumable and stock unit. Source-system mapping remains an integration requirement;
this implementation does not claim a live connector to KNL's existing ERP.

For every line, all quantities are in the PO stock unit, using exact Decimal with
four places. Received must be positive; accepted and rejected are nonnegative.
`received = accepted + rejected`. Unresolved inspection is unsupported and blocks
the import. This records the ERP inspection result; it does not inspect/approve it.

Each positive accepted quantity must match exactly one POSTED USABLE RECEIPT source
event with the same material, stock unit, timestamp and source actor. Existing M4.1
explicit unit conversion can normalize the stock event; exact conversion must equal
the GRN accepted quantity. Zero acceptance has no stock transaction. Damaged/rejected
quantity never generates a usable-stock movement.

## Fulfilment and over-receipt boundary

PO responses now include received, accepted and rejected totals summed from immutable
GRN lines. For issued POs:

`pending = ordered - sum(imported accepted quantity)`

These are imported figures, not a claim of complete live source coverage. Before the
first import, imported accepted quantity is zero and pending equals ordered. The
response exposes `fulfilment_is_live=false` and `pending_basis=IMPORTED_ACCEPTED_GRNS`;
the UI explains that missing ERP imports are not included. No planning engine uses
these totals as a shortcut around the M4.2 coverage/reconciliation checks.

The existing immutable PO commitment `status` remains DRAFT/ISSUED/CANCELLED.
A separate derived `fulfilment_status` is NOT_APPLICABLE for drafts/cancelled drafts,
NOT_RECEIVED when no accepted quantity is imported, PARTIAL when some is accepted,
and COMPLETE when every item is fulfilled. It is calculated from committed receipt
rows, so there is no independently mutable counter or status that can drift after
a rollback. COMPLETE is a receiving result, not financial/legal PO closure. Issued
cancellation, amendments and reversal semantics remain TBD and unavailable.

Until KNL approves over-receipt handling, an individual receipt's physical received
quantity above that line's current pending quantity is held with
`GRN_OVER_RECEIPT_TBD` (409), with no writes. This is an unsupported-case hold, not
an approved tolerance or an automatic rejection by the warehouse. Cumulative physical
receipts may exceed ordered quantity through replacements of previously rejected
material; cumulative accepted quantity must never exceed ordered quantity.

Synthetic example: ordered 60; received 22.1234, accepted 20.1234, rejected 2 leaves
39.8766 pending. Accepting 39.8766 replacement quantity completes fulfilment; total
physical received is 62 and accepted is 60. These are test values, not KNL golden data.

## Stock snapshots and double-count protection

Every GRN includes one authoritative usable snapshot for each material, at or after
the receipt time and no later than export generation. Source snapshots attest that
nonusable/reserved quantities are excluded. Missing snapshots block the whole import.
The balance service continues to select the latest source snapshot. It never adds
the receipt quantity on top of that already-reported figure or reconstructs an
opening balance from incomplete history. Older imports cannot regress current stock.

If the identical stock event or snapshot already arrived through M4.1 import, it is
reused with no duplicate movement. A stock transaction can link to only one GRN line.
Different content under an existing source key is a conflict. Previously committed
source imports remain valid if a later GRN import fails; every new effect of the
failed request rolls back.

Imported stock changes invalidate projection evidence through the existing M4.2
snapshot identity checks. New reconciled projection inputs are required where the
snapshot changes. This milestone does not automatically rewrite confirmed incoming
or subtract pending POs, so receipt/PO quantities cannot be added twice by this path.

## Storage, transaction and retries

Migration `0016_grn_imports`, parent `0015_purchase_orders`, adds:

- `grns`: unique stable ERP GRN key and canonical content hash; PO, supplier and
  stock import batch references; source event time/actor; importer, time and reason.
- `grn_items`: unique source line and PO item per GRN; material/unit; physical,
  accepted and rejected quantities; unique optional stock transaction link and
  mandatory authoritative snapshot link.

Foreign keys restrict deletion. Quantity checks and unique keys protect stored
records. PostgreSQL append-only triggers reject UPDATE/DELETE of GRNs and lines.
Existing applied migrations and PO/item immutability guards are unchanged.

The import uses a SERIALIZABLE database session. It locks the PO before reading
accepted totals, then locks affected consumables in UUID order through the stock
staging service. All receipts for the PO share its parent lock. Source records,
GRN/lines and both GRN/PO audit records flush and commit once. The stock staging
primitive does not commit. All exceptions roll back. Consequently PO totals and
derived status change only with committed GRN data.

Same source GRN key and canonical content returns the original receipt (200,
`replayed=true`); changed content conflicts (409). A new receipt returns 201.
Stable ERP document/event keys must survive adapter retries. Unique keys cover
simultaneous duplicates and stock events linked across different GRNs. Serialization
conflicts/deadlocks return 409 with an unchanged-request retry instruction; a retry
revalidates outstanding quantity. Never replace a source key to force through a retry.

## API, UI and permissions

| API | Required permissions |
| --- | --- |
| POST `/api/v1/grns/imports` | `purchase.grns.import` and `inventory.stock.import` |
| GET `/api/v1/grns` | `purchase.grns.read` |
| GET `/api/v1/grns/{id}` | `purchase.grns.read` |

List supports `limit` (1–100, default 25), `offset` and optional `purchase_order_id`.
Import supports 1–100 distinct PO lines belonging to one PO. Typed request/response
schemas are published in OpenAPI. Requests reject extra fields, binary floats,
excess precision, unsupported source states, missing source links and naive times.
POST is additionally gated by existing `INVENTORY_IMPORT_ENABLED` (default false).
No new environment variable is needed. Migration seeds two permissions without grants,
users or business values. Permission names do not confer external warehouse authority.

The `/grns` screen lists imported receipts, shows supplier/PO/material details and
audit source links, and previews a normalized JSON export before submission. It
preserves decimal text and the unchanged source payload for retries. The browser
accepts files up to 1 MB; imports must use the verified adapter contract. Loading,
empty, denial, validation, retry and replay states are visible. The PO screen shows
accepted/rejected totals, imported pending and derived receipt status.

Compatibility impact: existing PO routes are retained, but issued `pending_quantity`
is now numeric on an imported-data basis rather than null, and pending_basis changes
from FULFILMENT_NOT_CONNECTED to IMPORTED_ACCEPTED_GRNS. Received/accepted/rejected,
fulfilment_status and fulfilment_is_live fields are added. Consumers must show the
coverage limitation instead of treating imported totals as authoritative live stock.

## Adapter payload and operational activation

The POST envelope is `{source_grn_id, purchase_order_id, supplier_id, event_at,
source_actor, source_status: "POSTED", reason, items, stock}`. Each item contains
`source_line_id, purchase_order_item_id, consumable_id, unit_id, received_quantity,
accepted_quantity, rejected_quantity, source_event_id`. Use null for source_event_id
only when accepted quantity is zero. All business quantities should be JSON strings.

`stock` uses the existing M4.1 SourceImport contract: stable export_id, generated_at,
import_reason, matching movements and authoritative snapshots. It must contain only
the accepted GRN events and exactly one snapshot per GRN material. See OpenAPI and
the synthetic `receipt_payload` fixture in backend/app/tests/test_grns.py for a full
working payload; its values are not production defaults.

Before enabling real imports, verify source document/line/event identities, local
PO-item mapping, unit conversion and post-receipt usable snapshot semantics against
KNL exports. Reconcile all relevant receipts before operationally relying on pending
totals. Missing export mapping, over-receipt tolerance, corrections/reversals and
inspection-pending processing remain TBD. No invented values resolve these gaps.

Run Alembic upgrade/check and the backend GRN/API and PostgreSQL integration tests.
Downgrade removes GRN history; validate rollback only in a disposable database, not
as a production correction procedure. Actual validation results and review notes are
in `backend/M5_4_REVIEW.md`.
