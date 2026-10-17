# Domain Business Rules

## Requirement chain
`Production/PRD → Product → Plant → Route → Process → Consumable → Approved Rule → Calculated Requirement → Plant Confirmation → Approved Exception → Final Requirement`

## Initial rule types
- `PRODUCTION_RATE`
- `AREA_COVERAGE`
- `PACKING_RATIO`
- `TOOL_LIFE`
- `FIXED_QUANTITY`
- `PLANT_REQUEST`
- `MAINTENANCE`
- `MIN_MAX`

Do not hard-code logic based on a consumable name.

## Formula patterns

### Production rate
`Requirement = Production Quantity × Approved Consumption Rate`

### Area coverage
`Total Area = Production Quantity × Area Per Unit`
`Requirement = Total Area ÷ Coverage`

### Packing
`Requirement = Production Quantity ÷ Units Per Pack`

### Tool life
`Operations = Production Quantity × Operations Per Unit`
`Tool Requirement = Operations ÷ Tool Life`

Rounding must be documented per rule.

## Gross requirement
Conceptually:
`Gross = Production-Derived + Approved Special + Approved Maintenance + Approved Trial/Rework + Other Approved`

Never add the same normal demand twice.

## Projected stock
`Projected Stock(t) = Current Usable Stock + Confirmed Receipts Before t - Forecast Consumption Before t`

## Reorder concept
MSL is a protected floor, not the complete reorder formula.

Conceptually:
`Reorder Point = MSL + Expected Lead-Time Consumption + Approved Buffer`

## Net requirement
`Net Requirement = Gross Requirement + Target/Safety Stock - Current Usable Stock - Confirmed Incoming`

Do not subtract a pending PO twice.

## Purchase quantity
`Raw Purchase Qty = Target Stock at Receipt - Projected Available Stock at Receipt`

Then apply approved MOQ, pack-size, order-multiple and supplier rules.

### Company monthly Purchase Plan preview — owner decision 2026-10-17

For production-based monthly Purchase Plan rows that have not already been
submitted, KNL-Formula.xlsx Plan!AD4 / AE4 now defines a separate rule:
`gap = selected-month uploaded MSL + consolidated requirement − previous-month closing stock`.
If gap is positive, recommend `max(gap, selected-month uploaded MOQ)`; otherwise zero.
Value is quantity × Product Master rate when present. The owner explicitly selected
uploaded Stock Management MSL/MOQ, rather than deriving MSL from an assumed number
of working/MSL days. Pending POs, pack multiples, maximum caps and lead-time demand
are not operands in this formula. Missing/ambiguous source inputs remain unknown.

This dated monthly preview is not an assertion of usable stock at a future receipt
instant. Existing timed M5.1 assessment/submission, independent human approval and
immutable saved evidence remain separate and unchanged. Displayed calculation basis
distinguishes them. See [monthly formula contract](25_COMPANY_MONTHLY_PURCHASE.md).

## Actual consumption
Purchases are not consumption.

Approved stock-flow convention should be based on:
`Opening + Receipts + Inward - Closing - Outward ± Approved Adjustments`

Exact actual-consumption convention remains `TBD` until KNL confirms transaction
handling. Munees confirmed that a central-store issue is dispatch to a plant,
not automatically actual consumption; a usable plant return increases central
stock, while damaged returns do not. Only physically received and accepted
quantities increase usable stock; a PO commitment does not. Stock quantities
support up to four decimal places. KNL's 2026-10-04 answers assign opening, reservations, warehouse approvals,
documents, corrections and closed periods to the existing ERP. M4.1 imports
already-posted history and authoritative usable snapshots; it does not implement
local stock posting or infer balances from partial history. Damaged/rejected/
inspection-pending material is excluded outside this ERP. Snapshot exclusions must
be verified at the source, without double subtraction. Required unit conversion
uses explicit approved factors; actual factors and MSL approach thresholds remain
TBD. See `16_KN_BUSINESS_DECISION_REGISTER.md` and
`17_CENTRAL_INVENTORY_CONTRACT.md` for the current boundary.

## Approval
The engine calculates/recommends. Humans approve critical changes and purchases.
