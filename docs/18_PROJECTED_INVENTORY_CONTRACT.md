# M4.2 projected inventory foundation

Owner: Munees. Reviewer: Yathish. Company: KNL.
Branch: `feature/munees/m4.2-projected-inventory`.
Development plan approved by Munees. KNL business values and unresolved operating
policies are not supplied by that development approval.

## Boundary and inputs

The existing ERP owns MSL authority, stock/reservation reconciliation and incoming
supply evidence. M4.1 provides dated usable snapshots already excluding nonusable
and reserved material. M3.5 provides calculated requirements plus approved
adjustments by planning version, plant and material. Its current final response
contains totals, not dated demand. M4.2 never spreads those totals into days/weeks.

This is a backend foundation for one central-store consumable and one explicitly
selected planning version per calculation. API explanation is ready for M4.4 screen/
alert integration. It does not combine competing versions, post warehouse events,
edit company MSL, calculate purchase quantities or establish approval authority.

An immutable normalized source set ties all supplied evidence to:

- material and stock unit;
- latest M4.1 snapshot identity and exact source timestamp;
- selected requirement version and a fingerprint/manifest of its quantities,
  source rows, rule versions, adjustments and final approval evidence;
- verified coverage end, source reference and reconciliation evidence;
- optional dated demand allocation, incoming schedules, approved MSL history and
  supplier lead-time interval.

All quantities are exact nonnegative Decimal strings/integers in the stock unit,
at most four decimal places. No float conversion, invented unit conversion or
silent rounding is allowed. Projection totals can be negative and are not clamped.

## Reconciliation and timing

For each plant in the selected material/version:

`Final requirement = already fulfilled + reserved demand already excluded from usable stock + remaining dated demand`

Each component is explicit; missing fulfilled/reserved amounts are not defaulted
to zero. The imported allocation must cover every relevant plant exactly once.
Approved adjustments are already included in the final total and are not added
again. The source reference must establish that fulfilled and reserved portions
are disjoint, describe this same snapshot, and that reserved demand is actually
covered by the stock reservations excluded from M4.1. The application cannot infer
that correspondence from monthly totals; operational mapping remains a prerequisite.

Incoming quantities belong to unique source delivery-schedule identities, not
repeated PO header totals. Outstanding supply is the source scheduled quantity
less already received and cancelled quantities. Only CONFIRMED outstanding supply
enters the projection. UNCONFIRMED/CANCELLED rows are explained as excluded. Partial
receipts already included in the starting snapshot are never added again. An
explicit empty incoming list means source-verified no incoming; null means unknown.
Outstanding confirmed supply without a reliable availability timestamp after the
baseline blocks the projection rather than disappearing or becoming immediate stock.

The supplied timestamp means usable availability, not an assumed PO or truck-arrival
date. Date-only schedules must not be converted to artificial midnight timestamps
without KNL-approved timing semantics. Source timestamps must carry a timezone and
are normalized to UTC. Same-instant mixed receipt/demand/MSL events block the result
because the engine has no authority to choose their ordering. Same-kind quantities
at an instant are combined exactly and explained together.

## Formula and states

For source snapshot time `t0`, cutoff `t`:

`P(t) = S(t0) + sum(confirmed outstanding receipts where t0 < time < t) - sum(reconciled remaining demand where t0 < time < t)`

The cutoff is exclusive. An event exactly at cutoff is excluded with a reason;
timeline rows show before and after states for included events. A receipt after a
breach may recover stock but cannot erase the earlier breach. A shortage is visible
as negative projected quantity. Lead time by itself never creates a supply event.

At each event, select the MSL revision with the latest effective time at/before
that event. Missing MSL is unknown, not zero. Each revision includes source identity,
quantity, effective timestamp and approval reference. Earlier revisions remain in
immutable source evidence. There is no local MSL editor or assumed initial value.

- BELOW_MSL: projected stock strictly less than effective MSL.
- AT_MSL: exactly equal, reported separately; no automatic alert policy implied.
- ABOVE_MSL: strictly greater.
- UNKNOWN: effective approved MSL absent.

The first future breach records the first observed transition from at/above to
below MSL after the baseline. Current-below-MSL is a separate condition. A recovery
followed by another breach is detectable. If baseline MSL is unknown, the first
future breach remains unknown, even if a later MSL revision is available. The
"approaching MSL" alert threshold and equality-trigger policy remain TBD.

## Lead time

Optional lead-time evidence identifies an existing supplier/material mapping,
approved start event, start timestamp, usable-availability timestamp, calendar basis,
calendar reference and approval reference. Calendar/workday semantics come from the
source; this foundation does not derive a delivery date by assuming working days,
holidays or a supplier duration. It returns projected balance immediately before
the supplied usable-availability time when that time is covered. Outside coverage
or missing lead-time data is explicit. It does not calculate a reorder date or buffer.

## Missing/stale source evidence

No schedule yields `TIMING_UNCONFIRMED`, monthly final totals, no projected stock,
no timeline and no claimed future breach. Unknown incoming or reconciliation also
blocks calculation. Requests beyond verified source coverage are incomplete.
Missing MSL or lead time does not prevent stock arithmetic when demand/supply are
complete, but the related assessment is unavailable and has a nonblocking limitation.
`COMPLETE` describes stock arithmetic for the selected version/coverage, not all
KNL policies being configured. Consumers must inspect limitations and nullable fields.

Existing `PlanningVersion.approved_at`/`approved_by` must provide final approval
evidence; DRAFT/SUPERSEDED versions are ineligible. M4.2 does not populate these fields
or treat PLANNER/ADMIN labels as approval. If the current workflow has not supplied
final-version evidence, the result is `FINAL_REQUIREMENT_NOT_APPROVED`; coordinate
the upstream final-release contract with Yathish/Keerthi before operational use.

A changed requirement fingerprint or newer stock snapshot requires a new reconciled
source set. Existing evidence is never silently rebased. Every report is dated and
`is_live=false`. Source completeness, refresh cadence and staleness tolerances still
need operational confirmation; no expiry interval is invented.

## Storage, API and security

Revision `0012_projected_inventory` follows `0011_central_inventory`. It creates
`projection_input_sets` with immutable JSON source evidence, requirement manifest,
payload/final-requirement fingerprints, material/version/snapshot references and
authenticated importer/time. This stores calculation evidence rather than another
authoritative requirement-rule, reservation or purchase-order model. One source set
is selected explicitly; records from multiple sets are never cumulatively added.

PostgreSQL UPDATE/DELETE protection reuses M4.1's append-only trigger function.
Import and audit commit together. Unique source-set identities reject conflicting
reimports; identical retries return the existing row. A concurrent conflicting
insert returns 409 and can be retried unchanged to obtain the recorded result.
The API opens a PostgreSQL REPEATABLE READ transaction before reading source data,
so a report/import uses one consistent view while other requests change requirements.

| Endpoint | Grant | Purpose |
| --- | --- | --- |
| GET `/api/v1/inventory/projections/status` | `inventory.projection.read` | Capability and timing limitation |
| GET `/api/v1/inventory/projections` | `inventory.projection.read` | Explanation and projected timeline, or explicit incomplete result |
| POST `/api/v1/inventory/projections/inputs` | `inventory.projection.import` | Persist normalized source evidence; 201 new, 200 replay |

Projection GET requires `consumable_id`, `planning_version_id`, timezone-aware
`cutoff`; optional `source_set_id` selects evidence. Without source evidence it
reports baseline/monthly totals and limitations. Error responses follow the shared
sanitized contract. No PATCH/DELETE or MSL approval endpoint exists.

These are central, cross-plant planning permissions. Migration seeds only codes,
with no role grants or users. Plant-scoped users do not gain central access through
their role name. The operator must approve named grants. Imports additionally need
`PROJECTION_IMPORT_ENABLED=true` (default false), after verifying external mappings.
The example environment file contains names with blank values only.

Source schema limits are technical bounds: 500 plants, 500 total demand events,
500 incoming schedules, 200 MSL revisions per set. No business defaults are seeded.
Downgrade drops evidence history; use disposable schemas for migration round trips.

## Remaining KNL/Yathish decisions

1. Dated demand schedule or approved timing granularity; source timezone and event ordering.
2. Final-release eligibility and authoritative version approval evidence.
3. Fulfilled/reserved demand reconciliation against net usable snapshots, including
   any obligations from other versions/periods that affect the requested horizon.
4. Complete confirmed incoming export, schedule identities, partial receipts,
   cancellation/delay treatment and usable-availability timing.
5. Material MSL values/effective dates, exact equality/approach alert policies.
6. Supplier lead-time meaning, calendars, intervals and verified planning coverage.

The development approval enables implementing this contract, not treating those
unanswered operating policies as approved. Real source connectors remain TBD.
