# KNL three-upload workflow: assessment and company decisions

Prepared for Munees on 7 October 2026.
Source code reviewed: develop, commit 95a5d83.
Status: implementation assessment and questionnaire, not production acceptance.

## 1. Requested result

Replace routine spreadsheet planning with this application. The recurring manual
Excel inputs are:

1. `Prd. Order` — production schedule.
2. `Stk. statement Opening stock` — stock statement.
3. `GRN` — external ERP receipt evidence.

The application should validate those files, resolve approved masters and mappings,
calculate requirements, support required confirmations and approvals, assess stock,
MSL and lead time, recommend purchases, track orders/receipts, and refresh reports
and alerts. Existing approved human approvals remain in the workflow.

Munees clarified on 7 October 2026 that quantities in the Plant sheets, Tool Room,
PMD, NPD and HRD are generated/copied from calculations. Treat their routine
quantities as derived outputs to automate, not as additional recurring manual
uploads or independent extra demand. This records the owner's process clarification;
it does not supply or independently verify each source calculation.

This three-input request supersedes the PRD-only operating proposal in the earlier
`KNL_PRD_AUTOMATION_REVIEW_2026-10-07.md`. That file was already present and has not
been edited by this assessment.

The intended compatibility has three separate acceptance criteria:

- Input compatibility: accept the actual KNL export layouts without routine retyping.
- Calculation compatibility: reproduce KNL-approved results, with documented
  corrections where the workbook contains an error or an obsolete rule.
- Output compatibility: provide the required Plan/Summary/plant/supplier views and
  agreed Excel exports. Exact workbook layout reproduction requires explicit scope.

The current application does not yet meet all three criteria.

## 2. What three files can and cannot supply

These three recurring file types can support the requested workflow only with
approved standing configuration and enough source coverage.

- Product/plant/route/process mappings, consumption norms, dimensions, supplier
  constraints, MSL, lead time and approval permissions must be initialized once and
  maintained when their approved values change. They cannot be inferred reliably
  from a production quantity.
- Opening stock plus receipts omits later issues, usable returns, reservations,
  adjustments and corrections. Refreshing the same stock-statement file type can
  provide updated balances if KNL confirms its coverage and usable-stock meaning.
  Until refreshed, balances and alerts must remain explicitly dated.
- A stock summary provides period totals, not necessarily individual movement
  history. Do not manufacture individual issue/return transactions from its totals.
- GRNs describe material already received. They do not enumerate POs with no receipt,
  confirmed delivery promises, cancellations or rescheduling. Open incoming supply
  needs a complete source: orders maintained in this app, a connector, or an agreed
  initial import and subsequent update process.
- Plant/department quantities may be stored as literals because calculation results
  are copied into these sheets, as Munees clarified. Trace their original calculations
  and standing inputs; a literal cell does not establish a separate manual-demand
  workflow. Genuine exceptional demand retains its approved request process.
- Monthly production quantities do not by themselves provide dates for shortages
  or latest safe ordering. Dated demand or an approved scheduling rule is required.

No extra recurring spreadsheet input is assumed. KNL must identify how these
missing facts will be supplied within the requested operating model.

## 3. Workbook evidence

Source: `C:\Users\Muneeskumar\Downloads\1.Consumable plan- Aug '26 REV-1.xlsx`.
The workbook was opened read-only; no workbook values or formulas were changed.

| Source location | Observed evidence | Consequence |
| --- | --- | --- |
| `Prd. Order!A1:M6` | Four header rows identify month, issue date and revision. B = Part No., C = Item ID, D = description, E = August R1, F = August R0. The first product has R1 = 0 and R0 = 200. | Select one period/revision explicitly. Do not sum revisions or treat zero as missing. |
| `Stk. statement Opening stock!A3:L8` | Statement is From 01-Jul-26 To 01-Aug-26. E = Opening Qty., G = Receipt Qty., I = Issue Qty., K = Closing Qty. Location and category rows appear among records. | Confirm cutoff, location and balance column. Filter headings/subtotals rather than importing them as materials. |
| `Plan!S4` and `Plan!AB4` | S4 reads the statement's K column; AB4 reads S4 for August opening. | The workbook uses prior-period closing as the next period's opening. Importing column E because the sheet is named Opening stock would be incorrect for this example. |
| `GRN!A4:Y6` | N = Order Qty., O = GRN. Qty., P = Rejected Qty.; source IDs, dates, cancellation and modification fields exist. | Preserve distinct ordered/received/accepted/rejected meanings and cancellation evidence. Accepted meaning still needs confirmation. |
| `GRN!A5:O6` | One GRN number appears on rows for two different POs. | The receiving adapter must accommodate multi-PO source documents. A scan found 15 GRN document IDs associated with multiple PO numbers. |
| `GRN!P5:P473` | No positive numeric rejection example was found in this supplied sheet. | Obtain a real rejected/partially accepted receipt example before approving the receipt mapping. Blank rejection semantics remain to be confirmed. |
| `Plant II!G5:G6`, `Plant V!G3:G6` | Quantities are stored as literals; `Plan!AT4:BG4` collects them. Munees clarified that these values are generated/copied calculation results. | Treat them as derived outputs. Trace their original rules/inputs rather than assuming additional recurring manual requests. |
| `Plant V!C10:G10`, `Plan!C4:Z4`, `GRN!I8:O8` | The same CO2 item appears with CUM in the Plant V row, kgs. in Plan, and KGS in GRN. | Resolve whether this is a label error or an approved conversion; never invent a gas-volume/mass conversion. |
| `Plan!V4`, `BO4`, `BR4`, `BT4` | Several MSL/reorder formulas coexist. BO4 includes daily quantity plus a hold-days value. | KNL must identify the intended policy and correct any dimensional inconsistency. |
| `Plan!X1`, `U3` | Workbook uses 26 working days and 10 MSL days. | These are workbook inputs, not universal system defaults. |

This assessment traced representative dependencies. It did not independently
recalculate and certify every workbook cell or every material's manufacturing norm.

## 4. Current software findings

The PRD and Requirements routes now open workspace screens; the earlier placeholder
finding is superseded. Administration remains a placeholder.

| ID | Finding | Required engineering action |
| --- | --- | --- |
| E01 | Product-Plant Routes reads the Product master. Saving/importing a PRD workspace row only stores a textual product code in PRDRecord. | Add reviewed product-master onboarding and stable external identifier mapping. Missing mappings must block calculations with a useful message. |
| E02 | Running the current PRD header-detection code against this workbook recognized only product code and description. It did not recognize the revision quantity column. Subsequent code substitutes quantity 0, Plant 1, current month and V1. | Build a verified KNL layout adapter with explicit period/revision selection and row validation. Remove guessed data. |
| E03 | Running the GRN header detector against this workbook selected column N, Order Qty., as quantity instead of column O, GRN. Qty. It missed GRN/PO number headers and selected Supplier Id. as supplier name. | Use an explicit reviewed column map and actual workbook regression cases. Ordered quantity must never become receipt quantity. |
| E04 | Workspace PRD/requirement records do not establish the canonical PlanningVersion, PRDOrderItem and calculated requirement evidence needed downstream. | Promote validated staging through the existing authoritative planning and requirement services. |
| E05 | Requirements workspace invents 5%/10% requirements and MSL 10/5 when mappings are absent; mapped calculation defaults to factor 1 and uses different rule names from the domain engine. | Remove these fallback business values and reuse approved norm resolution and the requirement engine. |
| E06 | Requirements workspace sums all stock snapshots and sums ordered PO quantities as pending supply. | Use latest authoritative stock, qualified outstanding supply and time-aware reconciliation. Do not sum snapshots or count receipts twice. |
| E07 | Workspace calculation reads every undeleted PRD row; REPLACE affects all active workspace rows rather than a chosen period/revision. | Enforce version scope, immutable history, scoped replacement and repeated-import protection. |
| E08 | Goods Receipts workspace saves/imports GoodsReceiptRecord, separately from the transactional GRN/PO/stock service. | Connect the source adapter to authoritative receipt integration and visible source traceability. |
| E09 | Transactional GRN import currently requires one issued local PO per source GRN plus matching stock events/snapshots. The supplied external export includes historical external POs, multi-PO GRNs and no usable stock snapshot. | Design verified external PO/line mapping, multi-PO handling and receipt-to-stock-statement reconciliation; add migrations/contract changes where needed. |
| E10 | Alerts use fixed MSL 100, a 20% approach band and a fixed 3-day PO warning window; missing stock becomes zero. Evaluation is exposed as an on-demand action. | Use approved effective policies, missing/stale states, domain reorder results, import-triggered updates and reliable scheduled evaluation as appropriate. |
| E11 | Some master/PRD/requirement routes require login but do not enforce action permissions/plant scope. Development seeding grants all permissions to all roles. | Enforce one approved backend permission matrix and restricted account provisioning; test cross-role and cross-plant denial. |
| E12 | Dashboard aggregates quantities without consistent material/unit/version grouping. | Use meaningful counts or unit/material/period-specific totals. |
| E13 | Existing tests cover workspace behavior, not full KNL calculation parity or operational recovery. | Add company golden cases and domain, transaction, reconciliation, permission and recovery validation. |

Primary inspected files:

- `frontend/src/App.tsx`
- `frontend/src/features/mappings/ProductionMappings.tsx`
- `backend/app/services/prd_workspace.py`
- `backend/app/services/requirements_workspace.py`
- `backend/app/services/grn.py`
- `backend/app/schemas/grn.py`
- `backend/app/repositories/inventory.py`
- `backend/app/services/projection.py`
- `backend/app/services/requirements.py`
- `backend/app/services/alerts.py`
- `backend/app/services/dashboard.py`
- `backend/app/modules/masters/router.py`
- `backend/app/modules/prd/prd_workspace_router.py`
- `backend/app/modules/requirements/requirements_workspace_router.py`
- `backend/scripts/seed_dev_users.py`

## 5. Decisions already retained

Do not reopen these unless KNL requests a change:

- Company name KNL; one central consumable store.
- Existing ERP owns warehouse posting and GRNs; this application imports evidence.
- Only accepted usable receipts and usable returns increase usable availability.
- Rejected receipt quantity stays pending for replacement.
- Orders are commitments; plant dispatch is not automatically actual consumption.
- Exact Decimal arithmetic and four decimal places for supported quantities.
- No invented manufacturing rule, MSL, target, supplier value or safety buffer.
- Approved demand must retain calculation evidence before PO creation.
- Munees approved provisional M5.1 development behavior: explicit target at receipt,
  zero order for nonpositive raw need, MOQ followed by simultaneous pack/multiple
  compliance, with visible maximum conflicts. KNL numerical acceptance remains open.

## 6. Questions for KNL — first discussion

Answer Q01-Q08 first. They determine whether the three-upload workflow has enough
information to produce reliable results. An answer may be TBD; the dependent
feature then remains unavailable rather than using a guessed value.

### Q01 — What does the stock file mean, and when is it refreshed?

For the next month's starting balance, confirm the intended column and exact
as-of date/time. The supplied workbook uses previous closing quantity, column K.
Does this quantity already exclude rejected, damaged, inspection-held and reserved
stock? Which location rows belong to the central consumable store? Will the same
stock statement be uploaded daily, weekly, after receipts, or only monthly?
How will intervening issues, returns and adjustments reach the application?

Evidence requested: one annotated export showing the correct usable quantity,
location, exclusions and cutoff for a material. Specify whether revised statements
reuse this same third-party export format.

### Q02 — What exactly are the GRN quantity and identity fields?

Is GRN. Qty. physical received quantity or already accepted quantity? Is usable
acceptance GRN. Qty. minus Rejected Qty., or supplied separately? Does a blank
Rejected Qty. mean zero, not inspected, or unavailable? Identify a stable line key,
receipt/inspection dates and how cancellations, changes and reversals are exported.
Confirm treatment when a GRN references several POs, as in the supplied workbook.

Evidence requested: one accepted receipt, one partly rejected receipt, one cancelled
or corrected receipt, and an example of repeated export of the same document.

### Q03 — Where do all open POs and promised delivery dates come from?

Will future POs be created in this app and recorded in the existing ERP, or created
in the existing ERP and mirrored here? How are their identifiers linked? How do we
obtain opening outstanding POs, including orders with no GRN, remaining quantities,
supplier-confirmed dates, cancellations and date changes? A GRN's Order Qty. cannot
stand in for a complete open-PO register or line-level outstanding quantity.

Evidence requested: two open PO examples, one partly received and one not received,
including PO line identity, supplier, remaining quantity and confirmed due date.

### Q04 — How are PRD month, revision, zeros and repeated uploads interpreted?

Will users upload three standalone files or select these three sheets from a whole
workbook? Which month/revision is active? Does R1 replace R0's full schedule, or is it
an incremental change? What do zero, blank and an omitted product mean? Can schedules
change after approval or after a PO exists? Who authorizes that change?

Evidence requested: a real R0/R1 pair with the expected final quantity for three
products, including a zero, a blank and a changed quantity. Preserve old approvals
and orders; KNL defines what must be reviewed after a revision.

### Q05 — Which identifiers and mappings define a product and consumable?

Is Item ID the stable identifier, with Part No. retained as another reference, or
does KNL use another key? Can one part be made at several plants/processes, and how
is quantity assigned without duplication? Who maintains product/plant/route/process
and process/consumable mappings? May a new code be staged for review automatically?

Recommended engineering workflow: import new codes as candidates, validate and
approve their master records, then require mappings before planning. Never assign
an unknown product to Plant 1 automatically.

Evidence requested: the approved mapping list or named KNL owners who will review
an initial extraction from the existing workbook.

### Q06 — What are the approved formulas for every material category?

For welding, painting/coating, packing, tool life, fixed requirements and other
categories in scope, provide the inputs, dimensions, rates, units, rounding and
effective dates. Identify which workbook formulas are approved and which need
correction. Can existing master/formula tabs be migrated once after review?

Evidence requested: at least one independently calculated example per rule type,
including product, plant/process, production quantity and expected material demand.

### Q07 — Plant/department quantity origin: answered by Munees

On 7 October 2026 Munees confirmed that quantities in the Plant sheets, Tool Room,
PMD, NPD and HRD are generated/copied from calculations. Their normal values are
derived outputs; no additional recurring upload is proposed for them. Do not ask
the quantity-origin question again unless conflicting evidence needs resolution.

Engineering follow-through: trace those calculations through the workbook and
existing formula-map evidence. Where the source formula is not retained because
only its result was pasted, identify the exact material/output and missing source
before seeking a focused clarification. Do not invent a production percentage or
treat the same calculated quantity as an additional requirement. Genuine extra
requests remain separate from the normal derived output.

### Q08 — What demand dates and lead-time calendar are approved?

Are requirements monthly, weekly or dated? If monthly, does KNL approve an explicit
distribution rule, or should the app provide monthly totals without precise reorder
dates? Define workdays/holidays, lead-time start event, working versus calendar days,
and when a delivery becomes usable after inspection. Dates alone also need an
approved same-day ordering/cutoff convention.

Evidence requested: one dated requirement/receipt timeline showing the expected
first shortage and latest safe order point.

## 7. Questions for configuration and release

### Q09 — Which MSL, target and maximum rules should be used?

Identify the authoritative meaning and formula for MSL among the workbook's
different columns. Is a breach below MSL or at/below MSL? Is MSL a fixed quantity or
days of cover? What determines target at receipt and any maximum? Identify who
approves values and effective dates. Confirm how these relate to the provisional
M5.1 behavior already authorized by Munees.

### Q10 — What supplier constraints and supplier selection rules apply?

Provide material/supplier MOQ, pack size, order multiple, lead time and their units.
Distinguish mandatory constraints from descriptive pack information, not applicable
from unknown, and quantity per order from quantity per delivery. Identify how a
supplier is selected; do not assume the last GRN supplier is preferred. Confirm a
joint MOQ/pack/multiple example and handling when maximum stock would be exceeded.

### Q11 — What unit conversions and whole-unit restrictions are approved?

Provide canonical units and approved conversions for each relevant material. Resolve
the supplied CO2 CUM/KGS inconsistency. Identify materials that must be whole pieces,
packs or cylinders despite four-place storage, and where rounding occurs.

### Q12 — Which human decisions remain and who can make them?

List permission and plant scope for master/mapping/norm changes, imports, planning
promotion, confirmations, extra demand, purchase review, overrides, PO issue and
source corrections. Specify separate requester/reviewer requirements and delegation.
Automatic calculation does not itself authorize automatic purchase approval.

### Q13 — Which alerts should operate automatically?

For below-MSL, future breach, latest-order-date reached, overdue PO, stale uploads,
missing mappings and invalid imports: identify recipient roles, timing, severity,
acknowledgement, escalation/repeat behavior and channels (in-app/email/other).
Supply any warning lead windows. Define acceptable data age. Do not invent a 20%
stock buffer or a 3-day warning window.

### Q14 — What reports and Excel output layouts must match?

Specify mandatory views/columns from Plan, Summary plan, plant/department sheets and
supplier plans. Must exports preserve exact sheet names/order/format, or are matching
approved quantities and traceability sufficient? Are export cells values only or
must formulas remain? Identify expected differences from known workbook errors.

### Q15 — What value/pricing scope is required?

Identify the source and approval of unit rates, currency, valuation basis, rounding
and effective dates. Are tax/freight/discounts part of this phase or handled entirely
by the existing ERP? Do not automatically treat the last GRN rate as an approved
future purchase price.

### Q16 — Who owns operation, scale and recovery?

Provide approximate materials/products, rows per export, concurrent users, upload
frequency, hosting owner and required availability. Agree test versus production
environments, backup retention, acceptable data loss/recovery time, support ownership
and who signs off a release. Technical implementation choices remain the team's job.

### Q17 — Which company examples will establish acceptance?

Provide approved normal, zero-demand, missing-norm, revised-plan, low-stock,
incoming-before/after-need, MOQ/pack/multiple, partial/rejected GRN and duplicate/corrected
import cases. Include cases covering every manufacturing rule type in use. Each
case needs source rows, units, dates, expected requirement, stock, reorder and purchase
results, approver and explanation. A spreadsheet's cached result alone is not signoff.

## 8. Answer format

For each question copy and complete:

```text
Question ID:
Answer / TBD / Not applicable:
Approved by (KNL name and role):
Effective date:
Example with quantities, units and dates:
Source document or sheet/row reference:
```

Do not include passwords, connection strings, API keys or tokens.

## 9. Implementation sequence

1. Correct known importer/data-flow defects and define strict staging, missing-data
   states and source traceability. These engineering fixes do not require KNL to
   design code or approve guessed business rules.
2. Agree Q01-Q08; implement the three verified source adapters and initial reviewed
   master/mapping/norm migration. Preview errors before accepting a source batch.
3. Connect canonical planning versions, approved requirement calculation, plant
   workflow and dated stock/incoming reconciliation. Preserve revisions and approvals.
4. Integrate MSL/reorder/purchase engines with explicit configuration, traced demand,
   human approval, PO mapping and accepted-GRN reconciliation.
5. Add automatic recalculation/alert triggers with retry/deduplication, source-age
   monitoring, understandable dashboards and agreed exports.
6. Validate company golden cases and full role workflows; verify PostgreSQL rollback,
   concurrent imports, migrations, recovery and deployment before production release.

Outstanding questions can be answered by phase. The affected calculation or
integration must not be enabled for operational reliance while its required facts
are still unknown. This review does not authorize automatic POs or warehouse posting.

## 10. Actual verification in this review

- Executed the current PRD and GRN header-detection statements against the actual
  workbook rows without importing operational data. Confirmed E02 and E03 above.
- Backend tests: 11 passed; five deprecation warnings and one pytest-cache permission
  warning. Tests use isolated SQLite databases. The sandboxed launcher stalled and
  was stopped; the explicitly permitted run outside the sandbox completed.
- Frontend tests: 42 passed, 1 failed across six files. Failure:
  `masters.test.tsx`, `401 on a protected request clears the session and returns to
  login`, could not find the Masters link; the rendered page was already the login
  form. Root cause requires investigation; this is not proof of an authorization bypass.
  Initial sandbox execution failed on temporary-file rename permissions before tests
  ran; the permitted retry produced the results above.
- TypeScript build (`tsc -b`): passed.
- No operational database writes/migrations, application source changes or workbook
  changes were made for this review. The new file is this assessment document.
- This is not a complete security audit, production load test, Supabase backup/restore
  validation, PostgreSQL concurrency test or a full workbook parity certification.
