# M6.2 Inventory and purchase reports contract

Owner: Munees. Reviewer: Keerthi. Migration head: `0017_report_permissions`, after
`0016_grn_imports`. Reports read existing domain records and call the M4.2/M4.3/M5.1
domain services. They do not add a report data store or reimplement inventory or
purchase formulas in SQL or React.

## Report sources and meanings

| Report | Source of truth | Meaning and limits |
|---|---|---|
| Material stock | Latest `stock_snapshots` through the M4.1 balance service | Existing-ERP usable balance at the snapshot's `as_of`, imported time and export. No historical as-of query or live stock claim. Missing snapshot stays `NOT_IMPORTED`. |
| Projected shortage / MSL | M4.2 projection service | Returns the complete timeline, breach conditions and limitations for the selected material, planning version, cutoff and optional reconciled source set. Requirement timing and source coverage limitations remain visible. |
| MSL / reorder assessment | M4.3 reorder service | Passes supplied policy and lead-time evidence unchanged to the domain service. Missing policy/evidence remains incomplete; no operational default is selected. |
| Supplier purchase plan | Purchase approval, M5.3 saved M5.1 evidence, PO items and imported GRN items | One row per approved-demand submission, with supplier/material dimensions and recommendation, reviewed quantity, draft/issued/cancelled order, received/accepted/rejected and pending quantities. Legacy rows without evidence are marked unknown. |
| Pending POs | Issued PO items and imported accepted GRNs | Pending is issued quantity less accepted imported quantity, using the shared purchase-order domain function. Draft commitments do not count as pending; rejected receipts remain unfulfilled. This is non-live because the existing ERP owns receipt posting. |
| GRN history | Imported immutable GRNs/lines linked to PO, stock transaction and stock snapshot | Physical received, accepted and rejected quantities remain separate. Source event time and local import time are both shown. It covers only imported GRNs. |
| Recommendation vs approved vs ordered vs received | Saved M5.1 evidence, M5.2 approval, PO items, imported GRNs | Preserves each stage separately. A missing saved M5.1 record is not treated as zero. Recommendation and approval are not inferred from PO quantity. |

The supplier purchase plan is grouped by supplier/material/demand row and can be
filtered to one supplier; it does not combine different planning versions or
approval submissions into a fabricated aggregate. All quantity values remain exact
Decimal values at the domain's four-place precision.

## API and access

All endpoints are below `/api/v1/reports`:

- `GET /options/materials`, `GET /options/suppliers`, and
  `GET /options/planning-versions` provide bounded filter choices.
- `GET /material-stock`, `GET /projected-shortage`, and
  `POST /msl-reorder-assessment` provide inventory reports.
- `POST /purchase-recommendation-assessment` passes explicit M5.1 inputs to its
  calculation service; it does not create a PO.
- `GET /supplier-purchase-plan`, `GET /pending-purchase-orders`,
  `GET /recommendation-fulfilment`, and `GET /grns` provide purchase reports.

Inventory reports require `reports.inventory.read`; purchase reports require
`reports.purchase.read`. The M6.1 planned-vs-actual report uses the inventory read
permission. Permissions are seeded by migration but granted to no role by default.
Shared material and planning-version filter options accept either report permission;
supplier choices remain purchase-scoped.
Frontend visibility is convenience only; the API checks permission on every call.
Results include source/coverage status and remain non-live where the source ERP is
authoritative.

Submitted/event/PO-date `until` filters are exclusive. Purchase-flow reports accept
PO status (`DRAFT`, `ISSUED` or `CANCELLED`) and PO-date range filters; pending PO reports are
restricted to issued orders. Each selected PO's imported accepted receipts are
matched within that same status/date selection before pending is derived. Results
use bounded pages. Report reads use the
projection service's consistent database session. Current stock is latest-snapshot
only; historical stock-as-of reporting is not claimed.

## Indexes, performance and open decisions

Existing indexes support material/supplier/PO joins, approval references, GRN-to-PO
line joins and latest snapshot selection. This milestone adds no indexes without
query-plan evidence. If production query plans show report latency, evaluate indexes
for GRN event time, PO status/date and a composite approval supplier/material/status
access path before adding schema changes. Large reporting workloads may need measured
read replicas or bounded export jobs; this milestone introduces neither.

TBD: operational freshness threshold; historical stock-as-of source; company
definition of a consolidated supplier plan; overdue delivery semantics; operational
MSL and lead-time authority where none is supplied. No daily or weekly demand
spreading, safety buffer, target stock, reorder formula or PO action is added by the
report layer.

Run `pytest app/tests/test_inventory_purchase_reports.py` and the M6.1 report tests.
For PostgreSQL, apply `alembic upgrade head` and run `alembic check` using the
disposable validation database. Migration `0017_report_permissions` contains only
the two report permission definitions; it adds no business tables and assigns no
default grants.
