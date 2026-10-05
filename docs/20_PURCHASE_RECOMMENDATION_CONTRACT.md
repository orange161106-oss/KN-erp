# M5.1 purchase recommendation

Owner: Munees. Reviewer: Yathish. Company: KNL.
Rule version: `M5.1_V1`. Branch: `feature/munees/m5.1-purchase-recommendation`.

## Approval and scope

Munees explicitly authorized implementation using the proposed answers/assumptions
to the eight M5.1 questions, with later KNL corrections allowed. This authorizes
the provisional calculation rules below. It does not supply numeric targets,
supplier values, company calendars or independently verified KNL approvals.
Responses identify `policy_basis=OWNER_APPROVED_PROVISIONAL` and
`assessment_basis=SUPPLIED_EVIDENCE`. Approval references supplied with a request
provide traceability; they do not grant authority or install company configuration.

This milestone provides a backend calculation and explanation for a selected
supplier, consumable, stock unit and planning version. It reuses M4.2's immutable
source evidence and M4.3's explicit lead-time/calendar convention. It does not
create POs, allocate orders, compare suppliers, split orders, persist operational
recommendations, send alerts, set master values or change another team's workflow.

## Decisions for the eight questions

| Question | Provisional implementation |
| --- | --- |
| Target | Explicit stock quantity at receipt, with reference and validity. No formula/default; not automatically MSL. Target is a desired level, not a maximum. |
| MOQ | Minimum stock-unit quantity per selected supplier/material purchase. Applies only to a positive raw need. |
| Pack | APPLICABLE means a mandatory whole-pack increment in stock units. If descriptive only, explicitly declare NOT_APPLICABLE to quantity rounding. |
| Multiple/precedence | Simultaneous compliance with MOQ, pack and order multiple. No sequential rounding that can invalidate an earlier constraint. |
| Maximums | Explicit optional maximum order quantity and stock at receipt. Rounding conflicts require review; no override or silent capping. |
| Supplier | Caller selects an existing active supplier/material mapping. No preferred supplier inferred and no automatic comparison or split. |
| Receipt timing | Explicit initiation and usable receipt timestamps verified against supplied lead time. Use exact timestamps; same-time demand/supply/MSL ordering remains incomplete. No monthly/day spreading or assumed start-of-day availability. |
| Missing constraints | APPLICABLE carries a value; NOT_APPLICABLE explicitly means no restriction; UNKNOWN blocks a final recommendation. Known states require a reference. |

The actual values and unsupported rules remain KNL inputs. These choices can be
revised through a new versioned rule/contract and acceptance tests when KNL provides
corrections; previously supplied evidence must not silently acquire new semantics.

## Calculation order

1. Load M4.2 projection at the proposed receipt time inside its REPEATABLE READ
   transaction. Require eligible approved final requirements, complete timing and
   reconciliation, current snapshot/fingerprint and coverage. Do not add incoming
   supply or deduct demand/reservations a second time.
2. Validate active material, stock unit, supplier and supplier mapping. Every target
   and constraint uses that stock unit. Other units require upstream approved
   conversion; this API performs no invented conversion.
3. Require target/constraint evidence and lead-time validity covering initiation
   through receipt. Verify the receipt equals initiation plus supplied duration,
   applying the explicit M4.3 calendar convention where needed. A historical M4.2
   interval is not a reusable duration. Duration supplier must match the selected
   supplier and any supplier identified by the projection interval.
4. `raw_quantity = target_stock - projected_stock_at_receipt`.
5. Require all five constraint states plus confirmation that no additional supplier
   restrictions apply. Unknown is not zero and cannot become NOT_APPLICABLE.
6. If raw <= 0, recommend zero; MOQ does not create unnecessary purchases.
7. Otherwise `quantity_after_moq = max(raw, applicable MOQ)`.
8. Determine the smallest quantity at or above that lower bound which is a multiple
   of every applicable pack and order increment. Convert exact quantities to integer
   ten-thousandths, use their least common multiple, and round upward once. Without
   increments, use the lower bound unchanged.
9. Check supported quantity range, maximum order quantity and maximum stock at
   receipt (`projected_stock + candidate`). An unsatisfiable maximum returns CONFLICT
   with candidate visible and recommended_quantity null. The candidate is not an
   approved order or a recommendation to exceed the maximum.

Example: raw 13, MOQ 20, pack 12, multiple 10 -> lower bound 20, common increment 60,
recommended 60. Decimal example: raw 0.3003, pack 0.25, multiple 0.30 -> common
increment 1.50, recommended 1.50. No binary floating-point arithmetic or rounding
to a guessed unit occurs. Inputs support four decimal places, with no silent loss.
Raw/projected stock can be negative; it is not clamped. Purchase quantities must be
less than 100000000000000, consistent with existing NUMERIC(18,4)-sized inputs.
An oversized least-common-multiple candidate returns a conflict rather than overflow.

MSL is displayed separately. Missing effective MSL yields an incomplete assessment.
An explicit target below MSL is not silently replaced; TARGET_BELOW_MSL flags it for
review. This quantity calculation alone does not establish compliance with an MSL
timing policy or repair a breach before receipt. Existing overstock with raw <= 0
still recommends zero and reports EXISTING_STOCK_ABOVE_MAXIMUM when relevant.

## Receipt boundary

Projected stock is the existing usable balance immediately before the proposed
receipt: M4.2 includes confirmed outstanding receipts and remaining dated demand
strictly before that instant. The hypothetical purchase is never added to incoming
inputs. `stock_after_receipt` adds the recommended quantity exactly once and is a
hypothetical result, not a posted balance.

If positive demand, outstanding confirmed supply or an MSL revision shares the
proposed receipt timestamp, return RECEIPT_EVENT_ORDER_UNCONFIRMED. M4.2's exclusive
cutoff must not silently decide which event wins at that instant. Source ordering
must be resolved before recommending. A receipt beyond verified horizon, stale
sources or missing dated demand also blocks recommendation.

## API and explanation

`POST /api/v1/purchasing/recommendations/assess` is read-only despite its JSON body.
It requires the existing central `inventory.projection.read` grant, with no role-name
bypass. This is calculation access, not purchase approval authority. No additional
permission grants or users are seeded.

The typed request has material/version/source-set IDs, supplier/stock-unit IDs,
initiation/receipt timestamps, evidence validity, optional explicit target,
supplier constraints and optional ReorderLeadTime evidence. Missing optional
business evidence gives INCOMPLETE, not a manufactured recommendation. Each known
constraint requires a reference, including NOT_APPLICABLE. Constraints include
moq, pack_size, order_multiple, max_order_quantity, max_stock_quantity and a
CONFIRMED_NONE/UNKNOWN statement for other supplier restrictions. Unsupported
additional restrictions must stay UNKNOWN until implemented under an approved rule.

The response shows:

- Final requirement total, snapshot usable stock, projected stock at receipt,
  confirmed incoming included before receipt, and effective MSL.
- Selected supplier identity/code/name, lead time, target, every constraint state,
  raw quantity, MOQ-adjusted lower bound, common increment, rounded candidate,
  recommended quantity and hypothetical post-receipt stock.
- Rule/provisional-evidence labels, all calculation steps, nullable status and
  explanations/limitations. Quantities serialize as four-place decimal strings.
- The full request and M4.2 projection, including source snapshot, requirement
  fingerprint, source identities, included/excluded incoming and reconciliation.

Statuses: RECOMMENDED (including zero), INCOMPLETE (missing evidence) and CONFLICT
(no valid supported quantity under known constraints). Only recommended_quantity
is consumable as the calculation's result; null never means zero. `is_live=false`
preserves the dated-source nature of the assessment. Unknown totals are null.

Malformed quantities/times/states return 422; inactive masters, unmapped supplier
or stock-unit mismatch return 409. Existing source errors remain unchanged.
Database failures use the shared sanitized 503 response.

## Storage, integration and tests

No new table, migration, environment setting, persistent rule store or audit mutation
is needed for this read-only calculation. The single Alembic head remains
`0013_inventory_alerts` from merged M4.4. No frontend or M4.4 alert behavior changes. A later
persisted/approved purchase workflow must store immutable calculation evidence and
verify policy authority; returned references alone do not replace that workflow.

Tests cover raw <= 0, MOQ, pack and multiple independently/together, decimal
increments, minimality against finite enumeration, negative availability, max
conflicts, unknown constraints/target, huge increments, incoming counted once,
stale/untimed projection, same-time events, calendar/lead time, inactive masters,
unit/supplier validation, permissions, sanitized errors and PostgreSQL consistency
during a concurrent supplier change. Synthetic examples are development tests,
not a claim of KNL-approved production golden cases.
