# Central basic consumable planning — 2026-10-15

## Owner decisions and scope

Munees approved a direct Production for sale → Consumption Norms → basic requirement
workflow. Product–Plant Mapping and ProductProcessConsumable are not prerequisites
for this workflow. **Super Admin reviews one central plan** before inventory and
purchase assessment. Existing plant-bound plans, confirmations and adjustments remain
separate and retain their access checks and history.

For the supplied drill example, 100 production parts × No. of Process 2 is **200 final
consumable units**. No tool-life divisor is applied to that explicitly selected rate
formula. This is not authority to convert all existing formula families to one rate.

## Workbook review

`Basic_Consumable_Plan_Sheet.xlsx`, sheet `Plan`, was read without modifying it:

- 860 formatted worksheet rows; headers on Excel row 3; 825 populated source rows.
- No stored Excel formulas. All Prd. Order reference values are 1, and every Sch
  reference equals Prd. Order × No. of Process.
- 435 rows lack Part No; 574 lack Used Part No; 430 have process name 0.
- Rows 440, 441 and 828 lack material identifiers. Four identifiers are numeric.
- 59 repeated source identity groups need review. Neither repetitions nor incomplete
  rows are silently removed, summed, mapped or treated as valid norms.
- The file supplies no stock-unit, tool-life, approved rounding or effective-date
  evidence. Canonical stock units come from Consumable/Unit masters; the reviewer
  explicitly selects formula, effective date, rounding and import reason.

Used Part No (PRD Order), when supplied, is matched exactly to the canonical product
part number/code. Part No is the component reference in that case. If Used Part No is
blank, Part No must resolve one canonical product. An invalid supplied production
identifier does not fall back to another reference. Production imports retain exact
Part No + Item ID pair matching. No fuzzy matching or automatic master creation.

## Architecture and implementation

React/TypeScript screens call FastAPI services using SQLAlchemy/PostgreSQL. The
existing Decimal rule engine remains authoritative. No new formula engine or AI/ML
calculation was introduced.

| Area | Source and behavior |
| --- | --- |
| Norm maintenance | `services/rules.py`, `schemas/rules.py`, rules router and React `features/rules/`: canonical master selectors, editable references/parameters, search, filters, manual creation, saved versions and history. |
| Reviewed norm files | `services/norm_imports.py`, `schemas/norm_imports.py`: XLSX/UTF-8 CSV template, read-only preview/corrections, validation, explicit confirm, export. |
| Direct matching | `services/basic_norms.py`: exact canonical products and active/effective product/process/material norms, explicit stock units, ambiguity/error reporting. |
| Production and basic demand | `services/basic_planning.py`, requirements `basic_router.py`, `CentralProductionImport.tsx`, `CentralRequirements.tsx`: reviewed production, direct calculation, trace, aggregation and central review. |
| Existing integration | `CalculatedRequirement`, `RequirementCalculationError`, `PlanningVersion`, `requirement_approval.approve`, `plant_workflow.get_final_requirements`, `projection.report`, `purchase_recommendation.report`, `purchase_order.submit_demand`. |
| Purchase UI | `CentralPurchaseAssessment.tsx` calls the existing server assessment and traced demand submission, with explicit supplier/policy evidence and separate quantities. |

The former monthly requirement rows and manual plant request grids are not silently
converted into normalized basic calculations. Existing plans remain accessible through
their previous tabs. New imports carry `ImportBatch.validation_summary.workflow =
BASIC_CENTRAL_V1`; batches without that marker retain their former calculation path.

### Import and edit integrity

Norm import policy is **all-or-nothing**: every original populated row must appear
once in the reviewed row set. Invalid rows or unresolved duplicate identities block
the batch. Correct the workbook and re-upload when redundant rows need removal.

Preview/corrections do not write masters, norms or audits. Confirm re-reads the original
file, verifies its hash and source row set, revalidates masters and current norms,
and checks a database-state review token. Catalog and request locks serialize norm
version changes; master rows are locked before confirming. New versions and audit
records commit atomically. Repeating the exact reviewed submission returns its prior
result. Identical norms can be skipped; conflicts require explicit SUPERSEDE plus
update permission. Edits create new versions; protected source provenance cannot be
rewritten. An imported rate must remain equal to its approved process count, with
zero extra scrap for the Q × count formula.

The importer batches reads and writes. A 20-row synthetic import used no more than
10 SELECTs in the focused check; it does not perform a master/version lookup per row.

### Production, revisions and calculation

- Existing `prd_source.parse` handles the selected month/revision and exact numeric
  validation. Explicit numeric zero and owner-confirmed standalone dash markers are
  zero; blanks, negative values, errors and excess precision are rejected.
- Hierarchical company schedules reuse `parse_sales_schedule_data` with automatic
  customer seeding disabled. Exact aliases, block totals and grand totals must
  reconcile; zero subtotals are also checked. Flat files retain their existing headers.
- No plant, route, product or unit is inferred/created. Central PRD plant strings are
  empty and persisted calculated `plant_id` is null; no fake Plant 1 is assigned.
- Missing norms remain visible before import. Known production rows may be saved,
  but incomplete calculations cannot be approved or released for purchase.
- Latest production revision only can be calculated/approved. Older source and
  approved calculation evidence remain history. Source quantities, norm IDs/versions,
  parameters, effective date, rounding, steps and exact raw evidence are retained.
- Supported production-derived rule families retain their existing handlers, including
  the legacy bounded MIN_MAX branch. Stock-policy MIN_MAX and manual PLANT_REQUEST
  are not basic production demand. Results requiring more than four stored decimal
  places need explicit approved rounding; they are not silently truncated.
- Super Admin approval records actor/time/audit on the entire version. Null-plant
  PlantConfirmation rows are never created. Plant-only access cannot confirm central
  calculations. Central read/write routes and legacy access to central calculations
  enforce explicit operation grants.

### Inventory and purchase

Demand is consolidated per consumable before stock/incoming is applied once. The
existing normalized projection still needs a usable snapshot with damaged/rejected/
reserved exclusions, dated remaining demand, explicit incoming coverage, reconciliation
and effective MSL evidence. A monthly stock-statement workspace upload alone is not
automatically represented as this stronger source contract.

The purchase assessment retains the existing target-minus-projected-stock formula,
MOQ, simultaneous pack/multiple and maximum constraints, lead-time and approval
evidence. No monthly demand spreading, assumed zero incoming, default target or
guessed supplier policy is added. Missing or stale evidence remains INCOMPLETE;
the screen explains why and blocks traced demand submission. A newer production
revision invalidates the older central version for new purchase assessments.

The synthetic integration check uses 230 basic units, usable stock 100 and confirmed
incoming 50: projected usable stock after dated demand is -80. With explicit target
20, raw purchase need is 100; approved MOQ 120 and pack size 25 produce 125. These
stock/policy values are test fixtures, not KNL production defaults.

## API additions

Under `/api/v1/consumption-norms`: GET `/template`, GET `/export`, POST
`/import-preview`, `/import-confirm`, `/bulk-update`. Norm list/responses include
canonical product identifiers and audited reference fields.

Under `/api/v1/requirements/basic`: GET `/versions`, POST `/production-preview`,
POST `/production-confirm`, POST `/preview`, POST `/calculate`, GET
`/{version_id}/results`, `/{version_id}/sources`, `/{version_id}/export`.

Approval reuses `/requirements/planning-versions/{id}/approve`. Purchase reuses
`/purchasing/recommendations/assess` and `/purchase-orders/demand`. Backend
recomputes recommendation evidence on demand submission; retries retain the same key.

## Database and deployment

New additive migration: `c001_central_basic_planning`, joining the previously existing
`2762e6d553d3` and `e002_master_period_uploads` heads. It permits nullable
`calculated_requirements.plant_id` while retaining foreign keys/uniqueness and changes
the PRD quantity check from > 0 to >= 0. No historical rows are rewritten or deleted.
Downgrade refuses to invent plants or delete explicit zero rows.

After explicit owner approval, the connected database was updated on 2026-10-15 at
16:07:39 UTC (21:37:39 IST). Preflight confirmed revision `2762e6d553d3` and the
existing compatible master-upload schema. Alembic applied the outstanding
`e002_master_period_uploads` merge and `c001_central_basic_planning` in one transaction.
Independent verification through the application's connection confirmed the committed
revision, nullable calculated plant, nonnegative PRD quantity check and no remaining
migrations. Counts in eight existing business/history tables and protected foreign-key,
primary-key and unique constraints were unchanged; the application schema check passed.
No company workbook was imported or business record approved/deleted by deployment.
Unmigrated installations still return CENTRAL_DATABASE_SETUP_REQUIRED with an
actionable message. Applied migrations were not rewritten or blindly stamped.

## Verification and manual acceptance

Focused checks passed: 94 backend tests (including existing formula/workflow
regressions), 17 frontend tests, TypeScript check and optimized production build.
One unrelated pre-existing SQLite fixture in `test_verified_workflow` fails while
dropping the constrained products.item_id column, before exercising application code;
it was recorded and excluded from the final focused regression invocation.
Synthetic browser checks covered norms, production dialog, central results,
collapsed sidebar, purchase evidence fields and truthful saved-state indicators.
No real company file was imported or company business record approved/deleted in QA.

Manual sequence after database setup:

1. Register/review Product, Consumable, Process and stock-unit masters.
2. Consumption Norms → template/upload → correct every row → choose approved
   formula/date/rounding → confirm. Check saved versions and approved parameters.
3. Production for sale → Upload Excel → select sheet/month/revision and norm date →
   review product/norm matches and reconciliation → confirm.
4. Requirement → Central requirement plan → preview matching → calculate and save →
   inspect product details, consolidated quantities and errors → export.
5. Super Admin: Plant review → Central plan review → approve the complete latest plan.
6. Purchase → Central purchase assessment → select approved revision/material →
   verified inventory source/supplier/policy → assess → inspect separate demand,
   stock and purchase values → export → submit traced demand when complete/positive.
7. Use the existing approval queue, purchase order and GRN workflow afterward.

Boundaries: imports select one month/revision at a time. Combined-quarter allocation,
dated usage schedules and working-calendar evidence are not inferred from quarterly
totals. Bulk reference import explicitly supports the owner-reviewed Q × process
count choice; other formula families remain available through manual norm maintenance
and parameter editing. The raw reference workbook requires master/duplicate/rule
review and is not production-ready simply because it can be opened.

Owner UI clarification — 2026-10-16: Consumption Norms no longer includes the
"Test a consumption norm" calculation panel. Norm setup, import/export, reviewed
edits and version history remain available. Requirement calculations continue in
the Requirement module; existing backend evaluation APIs and formula logic are
unchanged.

## October requirement-view repair — 2026-10-16

The owner requested product-wise consumable quantities in both Central requirement
plan and Existing monthly plans → Consumable Planning Module. For a month whose
latest revision is BASIC_CENTRAL_V1, the monthly screen now reads the same saved
CalculatedRequirement rows and delegates Recalculate to basic_planning.calculate.
It does not maintain a second independent production-derived formula result.
Manual plan periods retain their earlier behavior/history. Direct requirement-upload
replacement is blocked for central production months; production and norm changes
must go through their source screens. Central read/write scope, latest-revision and
approved-history protection also apply through monthly endpoints.

The hierarchical sales parser previously invented "Nos" without a unit column,
while existing Product masters used PCS. New schedule imports obtain the matched
Product Master unit and record that provenance. Existing central schedule batches
are recognized by their specific historical metadata shape; only their fabricated
Nos default is interpreted using the current matched master. Saved production rows
are not rewritten. Calculation evidence records original unit, effective production
unit and its source. Explicit units from other import formats still fail on mismatch;
there is no general PCS/NOS conversion or unit equivalence rule.

Monthly queries now eager-load relationships and batch norm audit references rather
than querying per result/error row. Metadata identifies the production workflow and
counts its saved result/error rows. Central results/exports include Part No, Item ID
and product description, with searchable per-product required quantities placed
before compact configuration diagnostics. Missing-norm notices retain actual source
quantities and clear after a corrected recalculation. Norm formulas, rates, rounding,
stock netting and purchase formulas were not changed.

Read-only October verification found 509 source rows (185 positive), no saved valid
calculations and 1,018 stale stored errors. With the repair, a current preview returned
66 valid calculation contributions across 31 consumables, 142 source rows without
linked norms and 17 PROCESS_REQUIRED diagnostics, with no production-unit errors.
The preview took 3.09 seconds; loading the 1,018 old saved error rows through the
monthly service took 8.78 seconds on the connected database. These are single
observations, not a production latency guarantee. No company data was modified or
approved. Calculate and save must refresh the unapproved October results; genuine
missing norms/process choices require company-reviewed data.

Verification: 40 distinct focused backend checks passed across the import/central/
monthly suites and the new consistency file; 9 frontend checks and TypeScript passed.
The new checks cover fresh and legacy unit provenance, explicit-unit rejection,
shared quantities, history protection, batched error loading, per-product export and
central access through monthly endpoints. No database migration is required.

Follow-up live verification: the owner signed into the ERP panel and Calculate and
save was executed for October R0. The saved result is 65 consolidated source/process/
consumable lines from 66 norm contributions, across 31 consumables. The two views'
saved calculation IDs and quantities match. Errors are now 142 NO_CONSUMPTION_NORM
and 17 PROCESS_REQUIRED; the old 1,018 diagnostics and false production-unit errors
are gone. No approval or source-data rewrite was performed.

A successful save followed by a timed-out result read previously left stale zero
rows visible. Central now reports the committed save, removes obsolete results and
offers Reload results as a read-only recovery. A failed read never automatically
repeats calculation or enables approval without loaded results. Remote
connection setup still varied up to 25.09s in one observation; this repair does not
claim to eliminate provider/network latency.

Central revision/results and monthly metadata/record reads have a bounded 60-second allowance for the
observed remote connection delay; other GET requests retain 30 seconds. Pending
reads with different limits do not share incompatible cancellation budgets. The
manual-planner tab no longer fetches hidden MRP records, and monthly reload clears
stale timeout messages. Reload results also recovers an initial revision-list
failure when no revision is selected. Final focused frontend verification: 22
checks (10 central, 3 monthly, 9 loading), including result/revision recovery,
hidden-tab loading and timeout budgets. TypeScript passed. Writes remain explicit
and are never automatically repeated by this recovery.

Monthly metadata uses two database reads, combining version/workflow and actor
labels and counting saved lines/errors together. Central monthly records reuse the
selected revision and load only audit provenance columns, avoiding automatic audit
actor lookups; the record read uses four queries. Sixteen focused backend checks
passed across consistency/query-budget, manual monthly and direct norm workflows.

## Record-loading optimization — 2026-10-16

Two additive read APIs load each Requirement view through one authenticated request:
`GET /requirements/basic/workspace` returns central versions, selected_version_id
and results; optional planning_version_id explicitly selects an existing central
revision. `GET /requirements/workspace/view` returns records and plan_metadata for
the supplied month/year and existing filters. Full prefixes remain `/api/v1`.
Existing read/export endpoints remain compatible, and permission/central plant
scope checks are retained. No mutation, schema migration or formula change.

The central revision list uses one query with the same latest-across-all-versions
meaning. Session-pooler port 5432 now uses the documented bounded connection pool;
the shared hostname no longer incorrectly forces transaction-mode NullPool.
See validation/RECORD_LOADING_2026-10-16.md for configuration, measured samples,
worker execution, search debouncing, table virtualization and focused validation.

## Purchase Plan compatibility view — 2026-10-16

The owner's October Purchase Plan was empty because its loader only read
MonthlyRequirementRecord, while the central workflow persists CalculatedRequirement.
For a central month the Purchase Plan now consolidates the latest revision's saved
calculations by consumable and stock unit in one query. It does not copy records
into the manual table, reuse an older revision, turn configuration errors into zero
demand or choose an arbitrary supplier. Existing manual monthly plans retain their
previous calculation and queue-submission path.

Central quantities requiring an assessment are nullable rather than fabricated
zeros: stock, confirmed incoming, stock-adjusted raw need and recommended purchase.
The plan shows REQUIREMENT_REVIEW_REQUIRED until the version is approved, then
ASSESSMENT_REQUIRED until traced purchase demand is submitted through the existing
assessment. Latest submitted assessment/approval evidence is shown with its supplier
and saved quantities. This is historical assessment evidence, not current stock.
The table labels distinguish central usable-stock/incoming/raw-need semantics.
Exports preserve blanks and the planning notice. The compatibility submission API
cannot bypass the existing central assessment, approval or evidence requirements;
plant-scoped readers cannot use it to see or export central demand.

The page explains unmet prerequisites and opens the selected revision for central
review/assessment without a page reload or switching to another month's default.
Existing formulas, review decisions, inventory source contracts and supplier policy
evidence remain unchanged. A monthly stock statement alone is still insufficient
to assert usable stock, dated outstanding receipts and purchase policy.

Read-only connected-data verification returned October R0's 31 consumables from 65
saved lines, with 159 diagnostics (142 NO_CONSUMPTION_NORM, 17 PROCESS_REQUIRED) and
no central approval. No source records were rewritten, approved or submitted.

## Purchase Plan scrolling and reviewed edits — 2026-10-16

The owner requested working grid scrolling and cell/row editing, then explicitly
selected both purchase-field and consumable name/unit editing. The Purchase page
and nested grid now have bounded flex sizes; the grid owns both scroll directions,
with its footer and scrollbars inside the viewport. Central assessment and approval
tables retain their own available vertical scrolling. An actual loaded baseline
replaces the missing baseline that marked all 434 October cell values unsaved.

Right-click Edit cell/Edit row, double-click and Save/Ctrl+S reuse DataTable.
Editable columns are Consumable Name, Stock Unit (Master), Requested Purchase Qty
and Remarks. Names update the canonical Consumable name/description; units update
its unit reference and Product Master's output-unit display. These master changes
require independent master-update permission, use existing active unit codes and
retain stock-history/supplier-mapping restrictions. Previously unassigned units may
be filled later. Calculated requirement units/quantities and saved approvals remain
immutable; a changed master unit does not convert or relabel saved quantities.

Requested quantities are explicit review proposals, not replacement calculations
or automatic approvals. They retain their own unit and notes in purchase_plan_drafts,
unique by planning revision and material, with NUMERIC(18,4), optimistic version,
actor/time and AuditLog evidence. Once a material enters the approval queue, its
proposal quantity/remarks must be reviewed there; name/unit master checks remain
independent. The queue shows the proposal alongside the system recommendation.
Modify may prefill a same-unit proposal, but still requires the existing explicit
review action and reason. Export appends master unit/proposal quantity/unit/notes,
preserving the original column positions.

Additive API: POST /api/v1/purchasing/workspace/save?month=M&year=Y accepts edits,
expected draft version/name/master unit and a change reason. It verifies purchase
update authority, central/plant scope, latest revision and row membership. Batch
saves are atomic; stale edits, invalid units and restricted unit changes roll back
all changes. Pending reads cannot overwrite edits. Dirty state blocks period/load/
submission changes; failed saves retain corrections and offer an explicit Discard
changes and reload recovery.

Schema revision c003_purchase_plan_drafts follows c002_optional_catalog_stock_units.
The connected database has an external Alembic checkpoint 8c0f13ab0a53 absent from
this checkout; it was not stamped or rewritten. As with the existing master-upload
setup precedent, app.db.setup_purchase_plan applies only the frozen additive c003
table migration inside a transaction/advisory lock. Default execution is read-only;
--apply was explicitly used and created the empty table. The original marker was
preserved. Future deployments with the local ancestry can use the normal migration
chain; reconcile the external ancestry before any generic upgrade of that database.

Focused verification: 37 backend checks (save API, central/legacy purchase reads,
proposal audit/precision/concurrency, master permissions/history, catalog edits and
additive setup), 28 frontend checks, TypeScript and Vite build. A synthetic browser
fixture using the real shell/Purchase components verified both scroll directions,
last-row access, enabled right-click actions and row saving. It used sample records,
not company mutations. Read-only connected-data verification confirmed 31 October
consumables from 65 saved lines and zero proposal records; no company approval changed.
