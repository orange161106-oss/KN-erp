# KNL business decisions and confirmation questionnaire

Prepared: 2026-10-02. Coordinator: Munees.
Technical domain owners: Munees (inventory/purchasing), Keerthi (workflow/access),
Yathish (production/requirements). KNL business approvers must be identified by KNL.

This document records Munees's answers in this conversation and the remaining
questions to take to KNL. It does not declare an unresolved rule company-approved,
create production permissions, or authorize a deployment.

## KNL answers received on 2026-10-04 — current M4.1 scope

Munees supplied `INV_KN_Discussion_Answers_Updated.pdf` as KNL's answers and
corrected the company name to KNL. The original questionnaire below is retained
as discussion history; the following answers supersede earlier local stock-posting
assumptions. See [M4.1 implementation contract](17_CENTRAL_INVENTORY_CONTRACT.md).

| ID | KNL answer | Implementation consequence |
| --- | --- | --- |
| INV-01 | Damaged/rejected/inspection-pending material is manually checked outside the new ERP and omitted from stock records. | Import usable material only; no new condition or quarantine workflow. |
| INV-02 | Reservations and ordered stock are maintained in the existing ERP. | No reservation model; usable snapshots must already exclude reservations. |
| INV-03 | Opening stock/cutover is maintained in the existing ERP. | No local opening form or opening posting. Earlier C04 is superseded for this application's scope. |
| INV-04 | Past entries are allowed; closed months are locked. | No local business posting/backdating. Already-posted source history may be imported immutably, including historical closed periods. |
| INV-05 | Receipt/return authority and approvals belong to the existing ERP. | Import/read grants do not establish warehouse approval authority. |
| INV-06 | Issue/return references are maintained in the existing ERP. | Source event identities provide import provenance, without a duplicate business document-linking workflow. |
| INV-07 | Corrections/count differences belong to the existing ERP. | No local correction/adjustment posting; later source snapshots can report a corrected usable balance without rewriting history. |
| INV-08 | MSL/emergency approvals remain external; alert when stock approaches supplied MSL. | Exact approach threshold is TBD for M4.2/M4.4. The example 500/1,000 is neither a default nor a trigger definition. |
| INV-09 | Purchase-to-stock conversion is required. | Different units require explicit approved factor/reference. Real factors and rounding/whole-piece rules remain TBD. |

One central store, accepted receipts, usable returns, issue-as-dispatch and four
decimal places remain confirmed. Negative reported usable snapshots are rejected;
local stock-issue enforcement remains external. Source balances are authoritative
dated reports, not calculated from potentially partial movement history.

The normalized import foundation is approved for development. The real source
export/API, usable-field mapping and exclusion evidence must be verified before
imports are enabled operationally. No live connector or source availability is
claimed. The PDF's effective dates, examples/evidence and named approval details
remain TBD; KNL representatives still need to supply those operational details.

## How development can continue with TBD decisions

All project decisions do not need to be answered before development starts.
Each feature needs the decisions on which its behavior depends. We can build the
confirmed ledger, history, Decimal validation, audit, authorization checks and
transaction handling while unrelated milestones remain TBD.

A missing policy is never converted into an invented business rule, zero value,
automatic approval, or broad access grant. Affected operations stay unavailable,
or return a clear policy/data-not-configured result. Synthetic test permissions
and test cases do not establish KNL authority or production acceptance.

For M4.1, KNL's update above establishes the existing ERP as stock authority.
Build an immutable import/reporting foundation. A usable balance requires a
verified source usable snapshot; partial movement totals are insufficient.
Operational imports stay disabled until source mapping and access are configured.
This document does not authorize deployment or supply production grants.

Later answers can be incorporated. Some are audited configuration changes; others
need additive database migrations, API/UI changes, tests and data reconciliation.
Previously posted transactions and audit history must remain intact. New rules
need an approval source and effective date; historical recalculation or correction
is a separate approved operation, not a silent rewrite.

## Earlier answers supplied by Munees — retained history

These are confirmed for development by Munees, not a claim that KNL has signed off
all operating procedures. Do not repeatedly ask these same movement questions.

| ID | Recorded decision | Remaining boundary |
| --- | --- | --- |
| C01 | One central consumable purchasing/store ledger; plants have their own demand. | No plant floor-stock balances or transfers are authorized. |
| C02 | Issue means dispatch from central store to a plant and reduces central stock. | It is not automatically actual consumption; the plant-side usage/reporting convention remains open. |
| C03 | Only perfect/usable extra material returned by a plant is accepted as a stock-increasing return. | Damaged plant returns are not accepted into usable stock. Inspection, source linkage and disposition still need KNL procedures. |
| C04 | Opening records existing usable stock once before other movements. | Opening date, verified quantities, zero-opening handling and sign-off remain open. |
| C05 | Only physically received and accepted GRN quantity increases stock. | PO ordered quantity and rejected quantity do not increase usable stock. GRN acceptance, rejection and pending-PO procedures remain open. |
| C06 | Damaged and reserved material must be excluded from available usable stock. | How KNL records these, and quarantine/release details, are TBD. Munees does not know whether KNL currently tracks them separately. |
| C07 | Stock quantities support up to four decimal places. | Whole-piece restrictions and conversion/rounding rules per material still need confirmation. Excess precision must not be silently rounded. |
| C08 | Munees authorized using the recommended protection against a negative current stock balance. | This does not establish a safety-stock/MSL number, emergency override, or permission to issue below an approved MSL. |

Movement-date rules and posting/adjustment authority were explicitly left for KNL
confirmation. No default approvers, value limits or role grants were supplied.

## Answer format

For each question, provide:

```text
Question ID:
Answer, or TBD:
Approved by (KNL name/role):
Effective from:
Example with quantities, units and dates:
Evidence/reference (procedure, form or workbook):
```

Use `Not applicable` if KNL confirms the process does not exist. Use `TBD` if the
answer is unknown. If an existing team document already has a KN-approved answer,
provide its reference instead of reopening the decision. Do not include passwords,
tokens or other secrets in this questionnaire.

## A. Original M4.1 questions — answered/superseded as recorded above

Suggested discussion participants: KNL store lead, quality/inspection lead and the
person who authorizes stock changes. These are suggested contacts, not ERP grants.

### INV-01 — Material condition and exclusions

Which conditions does KNL actually track: usable, damaged, rejected, inspection
pending/quarantine, expired, or another condition? For each, say whether it is
physically held in central store and whether it is available to issue. Are unusable
items recorded somewhere today? Can they later become usable, and who authorizes
that release? Supply one real example. Until confirmed, no speculative condition
workflow is to be enabled.

### INV-02 — Reservations

Are consumables reserved for a plant, order or approved requirement? What creates
a reservation, how much can be reserved, and when is it released, cancelled or
converted into an issue? Can another plant use reserved material? Must availability
exclude reservations while physical stock still includes them? Supply one example
showing physical stock, reserved quantity and available quantity. Exclusions must
not be subtracted twice.

### INV-03 — Opening stock and cutover

What cutover date/time will be used, who verifies and approves the opening count,
and what is the source of the consumable-wise quantities and units? Does the opening
list already exclude damaged, held and reserved quantities, or list them separately?
How should zero-opening items and late discoveries be recorded? How will receipts
or issues during the physical count be reconciled without double counting?

### INV-04 — Movement dates and closed periods

May a user record a movement that happened yesterday or in a previous month? Who
can do this, what is the allowed date window, and are accounting/stock periods
closed? Are future-dated entries permitted as plans only, without affecting stock?
When a late issue is entered, must negative-stock checks apply only to the current
balance or also to every historical balance from its event date onward? Specify
the KNL reporting timezone and cutoff time as well.

### INV-05 — Posting and adjustment authority

Who may view balances/history, record opening, receive accepted stock, issue stock,
accept a usable return, and increase/decrease stock by adjustment? Which actions
need another person's approval before stock changes? Can a user approve their own
adjustment? What reason/evidence is mandatory? Name roles, plant/store scope and
the actual approving positions; do not infer this from ADMIN or STORE labels.

### INV-06 — Issue and plant-return documents

What document/reference proves an issue or usable return? Must an issue refer to
an approved plant request, and may it exceed the request? Are partial issues
allowed? Must a return link to an earlier issue, and must the cumulative return
be no greater than that issue? Who confirms the returned material is usable?
How are pre-system issues and their later returns handled? Plant destination is
traceability, not permission to create a plant floor-stock balance.

### INV-07 — Count differences and corrections

How often are physical stock counts performed? How are count differences reviewed?
If a posted movement is wrong, may it be reversed, and must the reversal link to
the original transaction? What happens if later movements depend on it, or a
reversal would cause insufficient stock? Specify approval and reasons. Never edit
or delete a posted transaction to hide a correction.

### INV-08 — Negative stock and safety-stock protection

Confirm KNL acceptance of the proposed negative-balance block. Separately, when
stock would fall below MSL/safety stock, is the action allowed with an alert,
blocked, or allowed only after an emergency approval? Who may authorize an
exception? A safety floor is different from zero stock; no threshold is invented.

### INV-09 — Units and indivisible materials

Which materials can be fractional, and which must be whole pieces/cylinders/etc.?
Are stock units different from purchase/issue units? If so, provide approved
conversion factors and who may change them. What should happen to stock history
when a material's unit changes? Four-decimal storage does not imply that fractional
pieces or automatic unit conversions are allowed.

## B. Inventory planning and reorder — M4.2/M4.3

These can be answered after ledger development, but before the dependent planning
calculations are enabled. Discuss with KNL planning, store and purchase teams.

### PLAN-01 — Meaning and ownership of MSL/safety/target stock

What do KNL's terms MSL, safety stock, target stock and maximum stock mean? Which
are actually used? Are they quantities or days of cover? Who sets and approves
them for each consumable, and from what effective date? Provide examples rather
than assuming these values are interchangeable.

### PLAN-02 — Demand timing

Is approved demand required on specific dates, by week, or only by month? If the
PRD is monthly, how does KNL distribute it across the month, if at all? Which days
are production days? If no approved spread exists, date-specific shortage/reorder
predictions cannot be produced by spreading monthly demand arbitrarily.

### PLAN-03 — Incoming supply

Which PO quantities count as confirmed incoming supply, and on which date? How
are unconfirmed, delayed, cancelled, disputed and partially received orders
handled? If receipt and issue happen on the same day, which timing/order does KNL
use? Accepted received quantity must not remain counted again as future supply.

### PLAN-04 — Lead time

From which event to which event is supplier lead time measured: PO placement,
approval, dispatch, arrival or acceptance? Is it calendar days or working days?
Does it vary by supplier/consumable? What calendars and holidays apply? What
should the system do when lead time is unknown or a delivery promise changes?

### PLAN-05 — Reorder condition and horizon

Does reaching exactly MSL trigger action, or only falling below it? How far ahead
must planning look? What happens if the latest safe ordering date is already past?
Are any uncertainty buffers approved? Give expected outcomes for one normal,
one exactly-at-MSL and one emergency case.

## C. Suppliers and purchase recommendation — M2.3/M5.1

Discuss with KNL purchase and store teams. Unanswered constraints remain unknown,
not zero, one or an invented supplier default.

### BUY-01 — MSQ and other terminology

Does KNL use MSQ? What is its full meaning, unit and exact calculation/application?
Is it a minimum, maximum or something else? Identify any other company-specific
term in the purchase workbook. Do not expand MSQ by guessing.

### BUY-02 — Supplier-specific constraints

For each supplier/consumable, define MOQ, pack size and order multiple separately,
including unit, permitted fractional values and what blank/zero means. Does a
pack describe its physical contents or a mandatory ordering constraint? Provide
approved examples where MOQ and pack/multiple are different.

### BUY-03 — Constraint precedence

In what order must MOQ, pack size, order multiple and maximum/target constraints
be applied? If they conflict, should the system block or choose a KN-approved
resolution? If net need is zero, should MOQ still cause an order? Supply examples
and expected final purchase quantities.

### BUY-04 — Supplier selection

Is the supplier chosen manually, fixed as preferred, or selected by an approved
price/lead-time/availability rule? Can one material be split among suppliers?
What happens when the usual supplier is inactive/unavailable? No automatic
selection is enabled without the approved rule.

### BUY-05 — Target quantity and recommendation overrides

How is target stock at receipt determined? Are there approved storage, shelf-life,
budget or maximum-stock limits? Can an approver buy a different quantity from the
recommendation, and what reason and approval is required? Keep recommended,
approved and ordered quantities separately.

## D. Purchase orders and GRN — M5.2/M5.3/M5.4

### PO-01 — Approval matrix

Who may approve/reject purchase recommendations and create/send/amend/cancel POs?
Does authority depend on value, quantity, consumable, supplier or plant? Are
multiple approvals needed, and can requesters approve their own requests? Provide
the actual approved limits and escalation/substitute rules; no limits are invented.

### PO-02 — PO creation and changes

How are PO numbers assigned? May an approved recommendation create multiple POs,
or may several approved demands share a PO? Which edits require reapproval after
a PO is sent? How are cancellations/short closures handled after partial receipt?
Which system is authoritative if the existing KNL ERP already issues the PO?

### PO-03 — Value fields

Which rate, currency, tax, discount, freight and other value fields are required
here? What are their approved precision, rounding and price-effective rules?
If this project does not own commercial accounting, identify what must simply be
referenced rather than duplicating another system's calculations.

### GRN-01 — Receipt versus acceptance

Who records arrival and who accepts/rejects material? Can quality acceptance occur
later or be partial? Where is inspection-pending/rejected material recorded, and
how does a later acceptance create stock exactly once? Which reference identifies
each delivery/line and prevents duplicate receipts?

### GRN-02 — Remaining PO quantity

Does pending PO quantity decrease on physical receipt or only on acceptance? If
part of a delivery is rejected, must the supplier replace it against the same PO,
or is it closed/credited? Provide one example with ordered, delivered, accepted,
rejected and remaining quantities. Accepted quantity alone increases usable stock.

### GRN-03 — Over-receipts and receipts without PO

Are quantities above the PO allowed, and with what tolerance/approval? Are receipts
without a PO allowed? How are split deliveries and unit differences validated?
What happens if two staff post receipts concurrently against the same PO line?
Transaction protection is technical; over-receipt entitlement is a KNL decision.

### GRN-04 — Supplier returns and later rejection

How are accepted goods subsequently returned to a supplier, rejected after use
inspection, replaced or scrapped? Which stock condition changes, which document
is needed, and how do PO pending quantities and commercial credits change? This
is separate from the confirmed usable plant-return movement.

## E. Production data and requirement rules — Yathish's domain

Several questions already exist in `14_PRD_REQUIREMENT_CONTRACT.md`. Link existing
approved answers rather than changing another teammate's contract unilaterally.

### REQ-01 — Actual PRD export and authoritative source

Provide an approved, representative export layout with column meanings, identifiers,
units, dates and revision markers. Which source is authoritative, how often is it
imported, and how are duplicate/corrected rows and invalid imports handled? Are
customer/work-order/model/drawing/delivery fields genuinely present and needed?

### REQ-02 — Product, plant and component mapping

Does every PRD row identify its plant? If the same product is made in multiple
plants, what allocation is approved? Does the export contain finished assemblies
or component/child parts, and is BOM expansion required? Who approves mappings,
process routes and consumable associations and their effective dates?

### REQ-03 — Formulas and norms

For each representative consumable, supply the exact approved formula, input
quantities/units, norm parameters, waste allowance if applicable, effective date
and approver. Explain applicability to product/process/plant. Unknown formulas,
including any gas/CO2 rule, remain blocked rather than copied from an uncertain
spreadsheet.

### REQ-04 — Rounding and aggregation

Does rounding occur per product/process/plant line or after material aggregation?
What method/increment is approved per material? How are whole containers, pieces
and unit conversions handled? Four-decimal ledger precision does not settle
requirement or purchase rounding.

### REQ-05 — Revision handling

When a new PRD revision arrives, which earlier version is superseded? What happens
to earlier plant confirmations, approved exceptions and already created purchase
commitments? Are additions carried forward or reapproved? Never count both
superseded and replacement demand as current demand.

## F. Plant workflow and actual consumption — Keerthi's domain

### FLOW-01 — Plant confirmation and additional demand

Who confirms each plant's calculated requirement, what is the deadline, and can
central planning proceed for confirmed plants while others are pending? Which
additional demand categories and supporting evidence are required, and who may
approve them? How is normal already-calculated demand prevented from being added
again as a plant request?

### FLOW-02 — Plant access and issue workflow

Which users may view or act for each plant, and who maintains those assignments?
Does a plant request/acknowledge an issue through this system, and can store staff
issue without acknowledgment? Are emergency issues a separate approved workflow?
No separate plant purchasing store is implied.

### FLOW-03 — Actual consumption evidence

How does KNL measure actual use after central-store issue? What records distinguish
used material, usable return, plant-held unused material and wastage? What period
and source does the planned-versus-actual report use? Issue quantity alone cannot
be labelled actual consumption.

### FLOW-04 — Official plant stock, if any

Does KNL maintain controlled plant floor-stock balances or official inter-plant
transfers? If not, answer `Not applicable`. If yes, describe records and authority
for a separately scoped future model; the accepted one-central-purchasing-store
decision remains unchanged.

## G. Access, alerts and reports

### ACCESS-01 — Complete role/action matrix

For ADMIN, PLANNER, PLANT_INCHARGE, STORE, PURCHASE, APPROVER and MANAGEMENT, list
allowed actions, visibility, plant restrictions and required approvals. Who creates,
deactivates and changes accounts/grants? Who can audit those changes? No role name
automatically implies every permission.

### ALERT-01 — Alert behavior

Which stock/reorder/PO-delay conditions require an alert, at what threshold, and to
whom? Is acknowledgement required? When should an alert resolve, escalate or be
sent again? Are notifications in-app only or also email/another channel? What
approved schedule is needed, if any? No duplicate-message spam or unapproved
notification transmission is implied.

### REPORT-01 — Required reports and definitions

Which reports/cards are essential, for which audiences, filters and reporting
periods? Define usable/on-hand/reserved, received/accepted/rejected/pending and
planned/issued/actual quantities precisely. What is each report's source of truth?
May management view cross-plant detail? What export formats and retention are
required? Never present missing information as a factual zero.

## H. Pilot, deployment and acceptance

### OPS-01 — Hosting and environments

Who approves the hosting/network environment, who supports it, and which staff
and locations must access it? Are separate development/test/staging/production
environments required? What availability, user count and expected data volumes
must be supported? The team can propose technical options once these needs are known.

### OPS-02 — Recovery and retention

How much data loss and downtime are acceptable? Who owns backups, restore tests,
incident response and audit/history retention? Are there company access/security
requirements to satisfy? Account recovery/session expectations need confirmation,
but secrets must be supplied through the deployment secret store, not this file.

### OPS-03 — Cutover and parallel operation

Which existing master, opening stock, reservations, open PO and receipt records
must be migrated? Which existing system remains authoritative during the pilot?
How will parallel recording be reconciled, and when may the old workflow stop?
Identify who signs off migrated quantities and outstanding commitments.

### UAT-01 — Approved examples and release sign-off

Provide KN-approved examples for normal/insufficient-stock issue, usable return,
damaged rejection, partial accepted GRN, count adjustment, concurrent submissions,
MSL/reorder, supplier constraints and unauthorized actions. Include inputs and
expected results. Which KNL representatives approve the pilot and operational
release, and what must pass before that sign-off?

## Suggested order for the KNL discussion

1. Answer INV-01 through INV-09 for operational M4.1. Start with classifications/
   reservations, dates and posting/adjustment authority; movement signs are already
   recorded above. Opening data and document references are needed for cutover.
2. Answer PLAN-01 through PLAN-05 before M4.2/M4.3 calculations are enabled.
3. Answer BUY/PO/GRN questions before dependent purchase and receipt workflows.
4. Have Yathish and Keerthi reconcile REQ/FLOW/ACCESS answers with their existing
   contracts. Existing implementations are not evidence of KNL policy by themselves.
5. Complete report definitions, golden examples and operational acceptance before
   production use of each affected feature.

Unrelated later milestones can remain TBD while the current milestone is developed.

## References

- `02_PROJECT_RULES.md`: central store, precision and approved business rules.
- `05_DOMAIN_BUSINESS_RULES.md`: formula concepts and unresolved actual consumption.
- `08_TEAM_OWNERSHIP.md`: domain ownership and shared-contract coordination.
- `10_TESTING_SECURITY_DOD.md`: approved rules, audit, security and acceptance.
- `13_AUTH_RBAC_CONTRACT.md`: permission categories and authority TBDs.
- `14_PRD_REQUIREMENT_CONTRACT.md`: existing PRD, formula and revision TBDs.
- `15_CONSUMABLE_SUPPLIER_MASTER_CONTRACT.md`: unit/supplier constraint TBDs.
- `KN_Consumable_ERP_AI_Build_Execution_Guide.md`: milestone dependencies and limits.


## M4.2 development approval and operational limits

Munees approved the M4.2 foundation plan with Yathish as reviewer. See
`18_PROJECTED_INVENTORY_CONTRACT.md`. This does not supply the unanswered PLAN-01
through PLAN-05 company values/policies. The implementation accepts explicit dated,
reconciled source evidence; monthly-only requirements report TIMING_UNCONFIRMED.
Operational projection imports remain disabled until real source mapping, final
release evidence, reservation/fulfilment reconciliation and incoming coverage are
verified. MSL authority stays with the existing ERP. Exact equality/approach alert
policy and lead-time calendars remain TBD; no daily spreading or buffer is assumed.

## M4.3 development approval and operational limits

Munees approved M4.3 reorder timing with Keerthi as reviewer. See
`19_REORDER_TIMING_CONTRACT.md`. A read-only assessment accepts explicitly supplied
policy/duration/calendar evidence and reuses M4.2's authoritative projection checks.
This development approval does not resolve PLAN-01 through PLAN-05. Approval
references in a calculation request do not verify company approval or install
operational policy. Missing inputs remain undetermined. No buffer, purchase quantity,
automatic order, local MSL authority or alternate company calendar is introduced.

## M5.1 owner-authorized provisional rules

Munees explicitly authorized proceeding with the proposed M5.1 assumptions while
allowing later KNL confirmation/correction. Reviewer: Yathish. The versioned
`20_PURCHASE_RECOMMENDATION_CONTRACT.md` records explicit target input, positive-need
MOQ, simultaneous pack/order increments, maximum-conflict handling, caller-selected
supplier and unknown-versus-not-applicable constraints. This is owner development
authorization, not a claim that KNL supplied numeric values or golden examples.
Targets, constraint values and calendar evidence remain explicit inputs; unknowns
block recommendations. No PO is created. Corrections require a reviewed rule version
and tests; supplied evidence must not silently change meaning.
