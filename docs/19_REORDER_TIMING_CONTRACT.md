# M4.3 reorder timing foundation

Owner: Munees. Reviewer: Keerthi. Company: KNL.
Branch: `feature/munees/m4.3-reorder-timing`, based on merged M4.2.

## Scope and authority

This is a read-only, deterministic timing assessment for one material and selected
planning version. It consumes the existing M4.2 projection service inside the same
PostgreSQL REPEATABLE READ transaction. It neither accepts client-calculated stock
nor rebuilds incoming supply, reservations or requirements. M4.2 stale-source,
final-approval, reconciliation, timing and coverage checks remain authoritative.

Policy and reusable supplier-duration inputs are supplied for each assessment and
echoed in the response together with the full projection/source evidence. The
`assessment_basis=SUPPLIED_EVIDENCE` label is deliberate: a caller-supplied approval
reference is traceability, not verification of company approval. This endpoint
does not persist or approve policy, publish an operational recommendation, create
an order, or execute an alert. Operational authority, policy ingestion and approved
configuration ownership remain KNL/Keerthi integration decisions. No role gains
policy-editing authority through this milestone.

## Endpoint and security

`POST /api/v1/inventory/reorder/assess` requires the existing central
`inventory.projection.read` permission. It is a read operation using a JSON body;
no database writes, new grants, table, migration or audit mutation are needed.
Permission checks are server-side and precede source access. Existing import
permissions and disabled-by-default projection imports are unchanged.

Request fields:

- `consumable_id`, `planning_version_id`, optional immutable `source_set_id`.
- Aware `evaluated_at` and exclusive `cutoff`; snapshot <= evaluation < cutoff.
- Optional `policy`: approval reference, effective interval, `violation` selected
  explicitly from BELOW_MSL / AT_OR_BELOW_MSL, and availability boundary selected
  explicitly from BEFORE_CROSSING / AT_CROSSING_ALLOWED. The policy must cover the
  whole snapshot-to-cutoff interval. Policy revisions inside it are not inferred.
- Optional `lead_time`: existing mapped supplier, approval reference, effective
  interval, integer `days`, explicit start ORDER_INITIATED and end MATERIAL_USABLE,
  and explicit basis ELAPSED_24_HOUR_DAYS / WORKING_DAYS. The approved duration must
  cover all required activities, including purchasing/transport/inspection where
  applicable. A M4.2 observed interval does not automatically provide this duration.
  When that interval names a supplier, the supplied duration must use the same one.
- A working-day duration additionally needs the calendar described below.

Missing policy/duration/calendar produces an incomplete assessment, not a business
default. Explicit zero lead time is allowed; it is never inferred. Day counts are
bounded at 3660 and calendars at 3661 dates for technical request/work limits.
Fractional, float and boolean day counts are rejected; finer duration semantics
remain unsupported rather than rounded. Unknown extra fields are rejected.

## Formula and decisions

M4.2 supplies exact four-place Decimal stock arithmetic and dated before/after
states. M4.3 compares those states using the supplied violation policy. It does not
add incoming again, subtract reservations again or calculate a purchase quantity.

Let B be the first future violation after evaluation. For an approved elapsed
duration L, the order deadline is B - L. For working days, use the explicit calendar.
No safety/uncertainty buffer is added. MSL changes can themselves cause a crossing.

- If stock violates policy at evaluation, `reorder_required=true` and
  `already_breached=true`. `expected_msl_crossing_at` reports evaluation with
  `crossing_time_kind=AT_OR_BEFORE_EVALUATION`; it is an upper bound, not a fabricated
  historical crossing. No retrospective safe order timestamp is claimed. A missing
  lead time does not suppress an already-observed violation of a supplied policy.
- A future violation yields `expected_msl_crossing_at=B`, kind EXACT_EVENT and
  `latest_safe_order_at`. At or after the deadline, reorder_required is true;
  before it, false. A later recovery does not erase the first future breach.
- With BEFORE_CROSSING, `latest_safe_order_inclusive=false`: the returned timestamp
  is the exclusive upper bound. With AT_CROSSING_ALLOWED it is inclusive. No tiny
  invented time buffer is subtracted to manufacture a latest valid instant.
- With no violation, false is returned only if the exclusive projection cutoff is
  strictly later than usable availability for an initiation at evaluation. Otherwise
  INSUFFICIENT_HORIZON returns null. False applies only within verified coverage.
- Incomplete/stale projection, missing policy/MSL or unresolved timing produces
  `status=INCOMPLETE`, `reorder_required=null` and explanation. Known crossing
  evidence may still be returned when only its order deadline is unavailable.

Evaluation uses after-event state for events at or before evaluated_at. Future
crossings are strictly after evaluated_at and before cutoff. This preserves M4.2's
exclusive projection cutoff. Existing same-time mixed-event ambiguity blocks the
projection; hypothetical availability at B is allowed only by explicit policy.
All timestamps normalize to UTC. Results remain `is_live=false`; no wall clock is
silently introduced. The source snapshot and evaluation date remain visible.

## Explicit working calendar convention

Supported convention: `UTC_DATES_START_EXCLUDED_END_INCLUDED`. The caller must
supply a source reference, approval reference, inclusive first/last dates and the
complete list of working dates in that coverage. Omitted dates are nonworking.
No weekend, holiday, locale, timezone or working-hours default is generated.

Both initiation and usable availability occur on working dates. Arithmetic
preserves UTC time of day and counts working dates excluding the start and
including the end. An initiation on a nonworking date moves forward to the next
listed working date at the same UTC time before counting. Backward calculation
subtracts that count from a working crossing date. If the crossing is nonworking,
an exact latest initiation would require additional intraday cutoff semantics;
return CALENDAR_COVERAGE_UNAVAILABLE rather than inventing them. Dates outside
calendar coverage also return that limitation. An empty list asserts no working
dates, not a default five-day week.

This is one supported explicit convention, not a declaration of KNL's calendar.
KNL local-time calendars, daylight-saving rules, intraday cutoffs, and any alternate
day-count convention require an approved contract before implementation.

## Integration and remaining decisions

No M3 requirements, plant workflow, supplier master fields, MSL values or applied
migrations change. Alembic remains at `0012_projected_inventory`. The returned
request plus projection contains the duration/calendar/policy references, source
set, snapshot, final requirement fingerprint and timeline needed to reproduce the
assessment while that source remains eligible. This is not durable calculation
history; any later persisted operational recommendation needs its own audited
contract and source/policy verification.

M4.4 can present the nullable assessment and explanations. No frontend changes are
included here. KNL must still confirm actual policy/equality behavior, availability
boundary, duration from initiation through usable stock, calendar conventions,
dated demand and complete planning coverage. M4.2 upstream approval/reconciliation
prerequisites remain. Supplied test values are synthetic, not KNL golden cases.

Tests cover short/long/zero lead time, exact deadline, no breach with adequate and
inadequate horizon, already breached, recovery, equality policies, incoming before
and after breach, partial receipts counted once, working dates/holidays, missing
calendar/policy/duration/MSL, stale requirements, expiration, validation and permissions.
