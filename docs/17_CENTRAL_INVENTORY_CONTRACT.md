# M4.1 central inventory foundation

Owner: Munees. Reviewer: Keerthi. Company: KNL.
Branch: `feature/munees/m4.1-central-inventory`.
Source: `INV_KN_Discussion_Answers_Updated.pdf`, supplied by Munees on 2026-10-04,
INV-01 through INV-09. This replaces the earlier assumption of local stock posting.

M5.4 adds [atomic posted-GRN import](22_GRN_INVENTORY_CONTRACT.md), linking ERP receipt
events and snapshots to PO fulfilment. It reuses this source-import boundary and
latest-snapshot balance strategy; no local warehouse posting is introduced.

## Authoritative boundary

The existing ERP owns opening/cutover, reservations, warehouse approvals, issue/
return documents, corrections, closed periods and safety-stock authority. Damaged,
rejected and inspection-pending material is handled outside this ERP. No new plant
stores, reservations, opening form, approval workflow or adjustment form is added.

This foundation imports already-posted central-store movement history and usable
balance snapshots from a normalized existing-ERP export. It never posts a warehouse
movement back to the existing ERP. The real export layout/API and mapping are still
TBD: this is an adapter contract, not a claim of a live source connector.

## Immutable data and balances

- `stock_import_batches`: unique export key, canonical payload hash, source generation
  time, authenticated importer, reason, UTC import time and new-record counts.
- `stock_transactions`: unique source event key, consumable/stock unit, source unit
  and quantity, explicit conversion factor/reference where needed, exact stock
  quantity and signed change, original event time/source actor and import batch.
- `stock_snapshots`: unique source snapshot key and `(consumable_id, as_of)`, nonnegative
  usable quantity in the stock unit, source exclusion attestations and import batch.

All three tables are append-only; PostgreSQL triggers reject UPDATE/DELETE. There
are no local stock create/edit/delete endpoints. A source key with conflicting data
is rejected, not silently replaced. Source corrections must arrive as a later
authoritative snapshot with a new key/time. No correction formula is invented.

The balance service selects the latest reported usable snapshot by source `as_of`,
never arrival order. Earlier imports cannot regress the reported balance. Missing
data is null/`NOT_IMPORTED`, not zero. Every reported balance includes its source
time, import time and `is_live=false`. Transaction totals are not treated as stock:
source opening, reservations and omitted history would otherwise cause incorrect
balances. No transaction is added again to an already-reported snapshot.

Snapshots must explicitly attest that nonusable and reserved material is already
excluded. If the existing ERP cannot provide that net usable figure, do not import
physical stock under the usable-stock label. No exclusion is subtracted twice.

## Movement and precision rules

Receipt: only accepted usable received quantity; positive stock change.
Issue: central-store dispatch; negative stock change, not actual consumption.
Return: accepted perfect/usable plant return; positive stock change.
Ordered PO quantity, damaged/rejected returns and inspection-pending material are
not importable stock movements. Opening and adjustment operations remain external.
Imported histories may predate import time, including already-posted closed-period
history. Importing immutable history does not authorize creating/backdating a new
business transaction in a closed month; those actions are unavailable here.

Quantities use Decimal/NUMERIC(18,4), a technical capacity of 14 whole digits and
four fractional digits. JSON quantities are decimal strings or exact integers;
binary floating input is rejected. Nonfinite, negative snapshots, nonpositive
movement quantities and excess precision are rejected without silent rounding.

Same-unit records use factor 1. Different source/stock units require an explicitly
supplied approved conversion factor and reference. Stock quantity is source
quantity multiplied by that factor using Decimal. Factors use NUMERIC(24,12).
Results outside stock capacity or requiring rounding beyond four places are
rejected; approved factors and any future rounding/whole-piece policy remain TBD.
No conversion or supplier defaults are seeded. Snapshot quantities are already
reported in the stock unit. Consumable unit changes are blocked once stock history
or a snapshot exists, preserving historical meaning.

## Transactions and permission checks

`inventory.stock.read` permits status, balances and history.
`inventory.stock.import` permits normalized source import only when operator setting
`INVENTORY_IMPORT_ENABLED` is true. Default is false; examples contain names only.
The migration seeds these two permission codes with no grants/users/company data.
Warehouse authority remains in the existing ERP; technical import permission does
not give purchase, GRN acceptance or stock-adjustment approval authority.

All affected consumables are locked in UUID order before checking source identities
and inserting a batch. Immutable source identities and export hashes prevent
duplicate/conflicting submissions. Data and audit records commit in one service
transaction; failures roll everything back. A retry of identical content returns
the original batch with no new rows/audit. Concurrent submissions are tested on
PostgreSQL, not inferred from SQLite behavior.

## API and React

- GET `/api/v1/inventory/status`: boundary and import capability.
- GET `/api/v1/inventory/balances`: paginated consumables with latest reported stock;
  literal code/name search and optional active filter.
- GET `/api/v1/inventory/balances/{consumable_id}`: one reported balance.
- GET `/api/v1/inventory/transactions`: paginated source history; optional material,
  movement and aware timestamp-range filters.
- POST `/api/v1/inventory/imports`: bounded normalized export, 201 new or 200 replay.

React displays reported stock/as-of dates, unavailable balances, filtered history
and an import panel only for technical importers when enabled. UI collects no
warehouse issue/return/adjustment approvals. Source IDs are technical provenance,
not a duplicate document-linking system. Responses use existing sanitized errors.

## Remaining decisions

Actual source export layout, exact usable-stock source field/exclusions, initial
snapshot data, approved conversion values and reporting/calendar details remain
to be supplied. Live refresh/staleness policy and named import/read grants require
operator configuration. MSL approaches/alert threshold and material values belong
to M4.2/M4.4; the example 500/1,000 is not a default or a trigger definition.
No purchase calculation, projected consumption, supplier values or plant stock is
introduced. Naming is KNL in displays/docs; existing DB names, package paths,
migration IDs and JWT issuer/audience stay compatible.
