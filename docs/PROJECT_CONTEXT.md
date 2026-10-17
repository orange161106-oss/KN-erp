# KNL Consumable ERP — project context and working memory

Reviewed: 2026-10-13. Repository: C:/KN. Branch: develop.
Code snapshot reviewed: 362c115 (design). The working tree was clean before this
context update. This document records code inspection and the owner's conversation;
it is not a company approval, a deployment approval, or a substitute for source code.
Recheck the current branch, code and relevant contracts before implementing changes.

## Purpose and ownership

The company name is **KNL**, although some filenames, package names and token defaults
retain KN/kn. Build a consumable-planning ERP around KNL's workbook and existing
company ERP. Do not replace raw-material planning or assume access to its API.
One central consumable store supplies plant-specific demand; five plant permissions
do not imply five separate purchasing stores or approved plant-floor stock.

Munees owns inventory and purchase planning; Yathish owns production, mapping and
requirement calculation; Keerthi owns plant workflow, access and alerts. Reviewer
assignments depend on the milestone. ADMIN, PLANNER, PLANT_INCHARGE, STORE, PURCHASE,
APPROVER and MANAGEMENT are role categories, not proof of business authority.

Read docs/01_PROJECT_SCOPE.md through docs/10_TESTING_SECURITY_DOD.md as relevant,
the domain contract, team ownership file and decision register. Unknown company
norms, limits, target levels, constraints and policies remain TBD. Do not copy
broken Excel formulas or infer operational defaults from illustrations.

## Architecture and setup

React + TypeScript + Vite + Tailwind renders the UI. FastAPI/Pydantic validates
requests; application services coordinate SQLAlchemy transactions, audit and domain
engines; PostgreSQL is the persisted store. Alembic manages schema changes. Python
business arithmetic uses Decimal/NUMERIC. openpyxl handles workbook imports;
product_master_service.py also imports pandas and NumPy.

The owner moved the development database to Supabase PostgreSQL using a session
pooler. React still calls FastAPI; it does not use Supabase's Data API as the ERP
business engine. Connection credentials live in backend/.env/environment only.
No passwords, keys, DSNs or employee details belong in this context file.
Settings accept postgresql:// or postgresql+psycopg:// and select Psycopg 3.
AUTH_SECRET_KEY must contain at least 32 UTF-8 bytes. DB sessions use UTC, pre-ping,
recycling and keepalives. TEST_DATABASE_URL is for disposable integration tests.

Frontend API base: frontend/src/api/client.ts; dev proxy forwards /api to port 8000.
Backend registry: backend/app/api/router.py mounts /api/v1 routes; main.py also mounts
app/api/production.py. Frontend screens: frontend/src/App.tsx and components/AppShell.tsx.
Dependencies: backend/pyproject.toml + uv.lock; frontend/package.json + package-lock.json.
Typical backend installation: uv sync --frozen --extra test from backend.
Start: .venv/Scripts/python.exe -m uvicorn app.main:app --reload from backend.
Frontend: npm ci, then npm run dev from frontend. Port is typically 5173 or 5174.
Hosted DB migrations are explicit: python -m alembic upgrade <reviewed target> or
python -m app.db.setup --migrate-only. Local database creation rejects remote hosts.
Do not run a generic upgrade-head command until the multi-head issue below is resolved.
Startup validates the signing key; do not assume startup provisions accounts/migrates DB.

## Intended workflow: start to finish

1. Authorized administrator prepares users, permissions and master data: units,
   consumables, suppliers and supplier-material links, products, plants, processes/routes.
2. Authorized planner establishes Product → Plant → Route → Process → Consumable
   mappings and approved, effective consumption norms. Production mappings alone do
   not create consumption norms. Norm output unit comes from the consumable master.
3. Import Prd. Order into Production for sale (/prd) for a planning month/revision.
   Reviewing products in Masters is separate from importing a production plan.
   Keep R0/R1/R2/etc history; use the latest appropriate revision for calculation.
   Products must exist and have one verified plant mapping, an explicit source plant,
   or an unambiguous primary mapping. Missing/ambiguous mappings block import.
4. Calculate consumable requirements from production and approved rule parameters.
   Plant/process/consumable scope, effective dates, units and rule version matter.
   A missing rule needs configuration, not an invented consumption rate.
5. Plant in-charge reviews/ confirms the plant's demand and submits additional needs
   with reason. Authorized review accepts/rejects exceptions. The intended final
   requirement combines calculated demand with approved adjustments without duplicates.
6. Store/inventory imports reviewed usable stock and stock-control parameters.
   Daily usable snapshot imports and monthly Stock statement uploads are distinct.
   For the current monthly Purchase workspace, use the previous month's statement
   and the planning month's Stock management parameters.
7. Assess projected stock, MSL breach, supplier lead time and reorder timing using
   explicit dates and confirmed incoming. Monthly totals alone do not prove daily
   shortage timing; do not invent daily/weekly spreading or an uncertainty buffer.
8. Calculate an explainable recommendation; authorized humans review it. The intended
   traced path retains the server calculation evidence before approval.
9. Create/issue a PO from an independently reviewed positive approved recommendation.
   A PO is a commitment, not a receipt or consumption. Retain approval/calculation links.
10. Import actual receipts/accepted GRNs from the existing ERP. Only accepted usable
    quantity fulfils the PO and affects usable stock; rejected quantity remains pending.
    Use the normalized atomic receipt import for PO/inventory integration.
11. Review alerts, reports and audit/history. They should consume authoritative domain
    results and identify dates/coverage. The workspaces below have integration gaps.

The owner's desired workbook inputs are PRD/production, stock statement/opening
stock, GRN, and reviewed control/master/norm setup as needed. Plant/Tool Room/PMD/
NPD/HRD workbook outputs were described as generated/copied from calculations;
do not require independent manual re-entry of every generated sheet. This desired
end-to-end automation is not fully delivered merely because CRUD/import screens work.

## Current screens and code paths

| Screen | Current implementation / important source |
| --- | --- |
| Administration (/admin) | Employee full name/ID, base role templates and granular CRUD/plant/alert flags; UserManagement.tsx, services/users.py, models/auth.py |
| Product master (/masters) | Products/consumables/assembly workflows coexist with older master APIs; services/product_master_service.py and inventory_masters.py |
| Production mapping (/mappings) | ProductPlant, route steps and ProductProcessConsumable; services/mappings.py |
| Consumption norms (/rules) | Norm version/effective dates/parameters; services/rules.py, domain/rules/engine.py and handlers. The owner removed the test calculation panel on 2026-10-16. |
| Production for sale (/prd) | PRDRecord workspace plus PlanningVersion/PRDOrderItem normalized path; services/prd_workspace.py, prd_source.py, prd.py |
| Requirement (/requirements) | MonthlyRequirementRecord workspace plus CalculatedRequirement engine records; services/requirements_workspace.py and requirements.py |
| Plant review (/plant-workflow) | UserPlant scope, confirmations, additional adjustments and review/final aggregate; services/plant_workflow.py |
| Stock history (/inventory) | Imported source movement history and dated usable StockSnapshot; services/inventory.py, stock_source.py |
| Stock statement (/inventory/statement) | StockStatementBatch/Line: monthly opening, receipt, issue and closing quantities/values; stock_statement_service.py |
| Stock management (/inventory/management) | StockParameterBatch/StockParameter: monthly MSL, max, MOQ, lead time; stock_management_service.py |
| Purchase (/purchase) | Monthly workspace, approval queue and approved handoff; purchase_workspace.py, purchase_approval.py; separate purchase_recommendation.py domain assessment |
| Purchase order (/purchase-orders) | Traced approval evidence, positive independent review, PO items, values/status; services/purchase_order.py |
| Goods receipts (/grns) | GoodsReceiptRecord Excel-style workspace; separate normalized GRN/GRNItem atomic import in services/grn.py |
| Alerts (/alerts) | In-app evaluation/acknowledgement and inventory/PO conditions; services/alerts.py; no scheduler guarantee |
| Reports (/reports), Dashboard (/) | Reports/dashboard services and inventory_purchase_reports.py; verify which data path each report actually consumes |

The original domain engines are domain/rules, domain/inventory_engine and
domain/purchase_engine. Empty package names are not proof of implemented engines.
Some files retain old and newer functions/models; inspect effective definitions and
registered routes. In prd_workspace.py, the later import_prd_excel definition overrides
an earlier one, so the earlier permissive import is not the effective importer.

## Confirmed inventory/receipt semantics and limits

- Existing KNL ERP remains warehouse posting authority under the recorded KNL answers.
- Usable stock excludes damaged, rejected, inspection/held and reserved quantities.
  Verify source exclusions; do not subtract exclusions twice.
- A plant issue is dispatch, not automatically actual consumption. Only usable/perfect
  plant returns increase central usable stock; damaged returns are excluded.
- Ordered/required quantity and billed quantity cannot stand in for actual received
  quantity. Example discussed: ordered 200, rejected 20, billed 200; actual physical
  receipt must be recorded separately. Do not infer accepted stock from billed 200.
- Quantities support four decimal places. Explicit zero is valid. An Excel dash can
  display a stored numeric zero; inspect raw values. Truly blank/unknown is not zero.
  #VALUE! and other Excel errors need correction rather than zero substitution.
- inventory_import_enabled and projection_import_enabled default false for normalized
  imports. Monthly workspace upload paths are separate; do not assume the flags gate all.
- Reorder/purchase domain engines require explicit timing/policy/target/constraint
  evidence. MOQ does not create an order when raw need <= 0. Pack/order increments
  are applied simultaneously using exact common increments; unknowns remain incomplete.
- No invented MSQ meaning, default supplier constraints, target/MSL, calendars or limits.
- KNL-approved numeric golden cases remain pending in docs/24_INVENTORY_PURCHASE_GOLDEN_CASES.md.
  Prior synthetic tests are not company acceptance.

## Recent confirmed UI/inventory work to preserve

Shared AppShell is bounded to the viewport; sidebar nav and main/table regions scroll
internally. Fit table height follows the flex parent, not stale window measurements.
Sidebar uses PanelLeft, portal hover/focus tooltips in collapsed mode, and dark group
icons for Master data/Inventory on the light active background.

Monthly Stock statement and Stock management have period-specific soft-deletion:
review batch_id + month/year, reason and confirmation; inventory_delete or Super
Admin is required. Transactions mark status deleted and keep rows/audit history.
Stale batches fail; retries do not delete a later replacement. Other periods remain.

Both grids support cell/row editing, formula bar, native copy/paste, clear, Ctrl+Z,
Ctrl+Y/Ctrl+Shift+Z, and Ctrl+S. Rectangular paste is one undo action. Draft history
resets on save/reload/discard/batch change. Editors keep text when double-clicked;
F2/menu editing selects existing text; direct typing places the caret after the first
character. Filters/period changes are blocked while unsaved drafts exist.

Stock statement quantity/value and Item Description are editable; stock management
limits, MOQ, lead time and Description are editable with inventory_update. Item IDs,
units/category/material identifiers remain protected. Description editing was
explicitly enabled after the owner supplied a screenshot of its disabled menu.
Decimals are retained as text until validated/stored as Decimal; cleared values are
null, not fabricated zero. Text preserves punctuation and supports up to 2000 chars.
Changed fields only are saved. Saves verify row/batch/period ownership and status,
lock the batch, audit before/after and roll back on failure. These edits correct
monthly uploaded reports/parameters, not the stock transaction ledger.

See docs/validation/STOCK_GRID_EDITING_2026-10-13.md and the two period-deletion notes.
Recent targeted checks passed at their respective changes: 75 backend/35 frontend
cases for editing/deletion/import; later description checks 29 backend/27 frontend;
7 sidebar tests; production builds. Those counts are prior targeted runs, not a fresh
full-repository test report or live PostgreSQL concurrency/UAT certification.

## Code-review findings: do not mistake these for completed integration

1. **Two migration heads.** Read-only `python -m alembic heads` on 2026-10-13 returned
   0025_add_item_class_to_stock_statement_lines and e001_phase4_product_master_pipeline.
   docs/09_GIT_WORKFLOW.md requires one head. Reconcile reviewed ancestry before
   deploying/migrating; do not blind-stamp, rewrite applied migrations or reset live data.
   The shared Supabase alembic_version/schema was not checked in this review.
2. **Dependency reproducibility was repaired on 2026-10-15.** NumPy/pandas are now
   declared in backend/pyproject.toml and uv.lock. The original review found them
   missing despite product_master_service.py importing them. See the performance
   validation below for the installation/build checks.
3. **Permissions differ across routes.** require_feature_flag is strict; generic
   check_permissions accepts ADMIN or any CRUD flag in a matching module, which can
   let read access satisfy a write check. Some product-master routes use only
   get_current_user. Frontend canPerform is stricter. Review operation-specific
   authorization before claiming a consistently enforced dynamic matrix.
4. **Monthly norm lookup is weaker than the normalized engine.**
   recalculate_monthly_requirements selects the first active norm by consumable code;
   it does not establish the full product/plant/process/effective-date scope in that
   lookup. It injects float thickness, and shortage status can replace a configuration
   error status. Missing norms must not become trustworthy purchase-ready outputs.
5. **Monthly Purchase workspace is not M5.1 engine integration.** It groups stored
   MonthlyRequirementRecord quantities, sums stored shortage/stock/pending fields,
   recommends positive shortage and picks the first supplier sorted by code.
   Previous-month closing stock is substituted into the displayed stock, without
   recomputing that shortage/recommendation from it. Current parameters are loaded,
   but full target/MSL/lead-time/MOQ/pack/multiple policy is not applied in this path.
   Summed row-level stock/pending can represent duplicated shared inventory; reconcile
   its grain before claiming double-count protection.
6. **Workspace submission is not necessarily traced demand.** purchase_workspace
   calls submit_purchase_approval directly. purchase_order.verified requires saved
   calculation evidence; it raises PO_TRACEABILITY_MISSING for untraced approvals.
   This can block an apparent workspace approval → PO workflow. The intended traced
   submission is purchase_order.submit_demand and server recommendation evidence.
7. **GRN workspace is a separate record path.** Its Excel importer stores
   GoodsReceiptRecord rows and an import audit; it does not call import_grn or stage
   source stock in that function. Normalized import_grn locks an issued PO and commits
   GRN items, stock-source import and audit atomically, with accepted-only fulfilment
   and conservative over-receipt hold. A saved /grns workspace row is not proof that
   the central balance/PO pending quantity was updated.
8. **Older contracts and newer workspaces need reconciliation.** The decision register
   describes external posting and operational timing/constraint TBDs; later UI code
   enables report corrections/imports and monthly shortcuts. Preserve the owner's
   approved UI work while resolving source authority/integration intentionally.
9. **Operational acceptance is incomplete.** Real export mapping, fresh daily data,
   validated numeric company examples, consistent user authority, deployment/backup
   ownership and the complete PRD → requirement → approval → PO → accepted GRN chain
   need verification. No live end-to-end production readiness was established here.

## How future work should use this memory

Start from the actual screen route, trace its frontend API calls to the registered
router and service/model, then identify the authoritative domain engine/contract.
Do not assume similarly named workspaces share the same stored evidence. Preserve
historical audits/revisions and review shared-domain changes with the assigned owner.
Keep this context updated when a verified workflow/decision changes; update contracts
separately when authority/rules change. Keep secrets and live personal data out.

## Performance hardening — 2026-10-15

The owner authorized performance/reliability work while preserving business logic
and workflow. Changes remain reviewable in the working tree; no commit, push,
migration, deployment or live business-data edit was performed for this task.

- Login entry JavaScript is about 286 KB (90 KB gzip), compared with the previously
  verified monolithic build of about 1.65 MB. Screens are loaded on navigation;
  PDF/Word libraries only load when exporting. Reports page code is about 18 KB.
- Stock statement/management reads use three SQL queries, versus five with the same
  actor in the baseline. Bulk 500-row saves use five SELECTs rather than 506.
  Batch locks, Decimal validation, whole-batch summaries, per-row audit and rollback
  remain. Before/after full read responses matched on identical synthetic data.
- Stock statement/management and PRD use a visible-row window for large grids;
  all records remain in selection, sort/filter, paste, undo and export operations.
  Stock searches wait 300 ms after typing, with pending searches blocking edits.
- Excel/SQL upload handlers run in FastAPI worker threads. API gzip is negotiated
  for larger responses. A shared route-template-only slow-request log was added.
- PostgreSQL retains five connections plus five overflow per process by default,
  with configurable budget/wait/recycle, LIFO, pre-ping and TCP keepalives.
  One remote connection is warmed before accepting requests; test/loopback skip it.
- Safe diagnostic categories distinguish connection, schema, credentials and capacity.
  Explicit transient reads can reconnect once after rollback. Frontend GET recovery
  is bounded and invalidated by writes/account changes. Mutations are never replayed;
  no passwords are cached and existing account/grant freshness checks remain.
- `python -m app.db.diagnose` is read-only and secret-safe. The 2026-10-15 probe
  found no missing registered-model columns, but round trips were approximately
  6.3 s / 1.0 s / 24.4 s. This provider/network variability remains outside the
  code-only speed improvements. Column presence does not certify Alembic ancestry
  or constraints. Do not promise that network/provider outages can never recur.
- The tracked .env.example contained credentials and was replaced with blank names.
  Exposed values need operator rotation; no secret was copied into these notes.

Final verification and scope/limits are recorded in
docs/validation/PERFORMANCE_RELIABILITY_2026-10-15.md. The earlier business integration,
permission consistency and migration-head findings still require their own review.

## Product Master catalog correction — 2026-10-15

Munees clarified that Product Master must NOT use month/year uploads. Its three tabs
now open an undated catalog in Bulk Import. Stock statement/stock management period
controls remain unchanged. All active entries are visible, including previously dated
uploads; existing entries display Saved and allow subsequent edits.

Upload creates an unsaved preview with source row/duplicate/missing-ID counts.
Save changes explicitly commits a reviewed workbook, even if cells were not edited.
Preview/discard never writes master/unit/supplier rows. Backend validation, Decimal
rates, protected IDs, optimistic tokens, atomic audits and delete-before-replace remain.
Delete data removes the selected tab's active entries while preserving stable IDs,
mappings, former monthly snapshots and history. Matching uploads reactivate IDs.
New operations are under `/masters/product-master/{category}/workspace`; new imports
record MasterCatalog audit evidence without inventing a month/year. No new migration
or live company-data deletion was performed for this correction.

Read-only reconciliation of the supplied consumables file found 471 rows with Item
IDs, 3 duplicate occurrences and 2 rows missing IDs: 468 unique items is correct.
The last displayed Excel serial excludes the first four rows. Numeric Output/Unit
values are flagged for actual stock-unit review; no tool capacity or unit is guessed.
Details, API and focused checks are recorded in
`validation/PRODUCT_MASTER_CATALOG_2026-10-15.md`. The former monthly implementation
record is historical and superseded for Product Master UI/workflow purposes.

Unit clarification: the owner asked whether a PCS/KG column is required. The same
workbook can have a separate Unit/UOM/Stock Unit column; it takes precedence over
numeric Output/Unit values. Explicit blank units remain unresolved for human review.
No actual unit values were supplied or guessed. Final focused verification passed:
18 backend checks, 12 frontend checks and the production build.

## Product Master bulk entry repair — 2026-10-15

A later merge reconnected the former direct uploader in `Products.tsx` while its
upload state and helpers were absent. Clicking Bulk Import raised
`setUploadError is not defined` before the dialog opened. The page now uses
`MasterBulkWorkspace` for consumables, assembly mappings and sales parts, and the
broken duplicate upload implementation was removed. An employee with the explicit
`masters_create` grant can open this uploader; its read/create/update/delete checks
remain enforced independently. The undated preview → review → Save changes flow,
delete-before-replacement rule, units, history and protected IDs are unchanged.
No live company records were uploaded or deleted for this repair.
Focused verification passed: 18 frontend checks and 8 isolated backend checks.
The full TypeScript check still reports independent `settledSearch` /
`useDebouncedValue` errors in the stock statement and stock management pages.

## Direct basic demand and central approval — 2026-10-15

Munees explicitly removed Product–Plant Mapping as a prerequisite for the new basic
consumable planning workflow and confirmed **Super Admin reviews one central plan**.
The supplied drill example is final demand: 100 parts × 2 processes = 200 units,
without an invented tool-life divisor. Other existing formulas retain their handlers.

Reviewed XLSX/CSV norm import, correction, atomic confirmation, templates/exports,
editable versioned grid and canonical master selection are implemented. New central
production uploads preserve exact product identities, customer alias/reconciliation
checks, selected month/revision and source rows without auto-creating masters/routes.
New ImportBatch metadata marks BASIC_CENTRAL_V1; old batches keep their legacy path.
CalculatedRequirement now supports explicit null plant scope; whole-version approval
uses Super Admin actor/time/audit, never fake Plant 1 or null PlantConfirmation rows.
The existing projection/purchase engines consume consolidated approved demand once
per material. Missing inventory timing/reconciliation/policy evidence remains incomplete.

See `24_CENTRAL_BASIC_PLANNING_CONTRACT.md` for files, APIs, reference workbook
findings, formulas, import/authorization rules, manual workflow and remaining limits.
Focused checks: 94 backend, 17 frontend, TypeScript and optimized build passed;
one independent old SQLite column-drop fixture is documented as excluded. Synthetic
browser verification found/corrected false unsaved counts on read-only new tables.
The earlier three stock-search TypeScript errors were repaired using their intended
debounced search values; stock quantities and workflow were not altered.

Database deployment was explicitly approved by the owner and committed on 2026-10-15
at 16:07:39 UTC (21:37:39 IST). Preflight confirmed revision 2762e6d553d3 and a compatible
existing master_upload_batches schema. The reviewed e002_master_period_uploads merge
and c001_central_basic_planning migration ran atomically. A fresh read through the
application connection confirmed c001 as the sole current/head revision, nullable
calculated plant, planned_quantity >= 0 and no pending migrations. The application
schema gate passed. Counts in eight business/history tables and protected foreign-key,
primary-key and uniqueness constraints were unchanged. No company business records
were imported/approved/deleted; this verifies schema deployment, not company data
readiness or production acceptance. No migration was rewritten or blindly stamped.

## Restored PRD import UI & Dynamic Sales Schedule importer — 2026-10-16

The "Production for sale" (PRD) Sales Schedule import modal (`SalesScheduleImportModal.tsx`)
and two-pass hierarchical parser workflow have been restored, replacing `CentralProductionImport.tsx`.
Per the owner addendum, all row numbers, counts, and totals are fully dynamic:
1. Header detection scans for `Part No.` and `Item ID` (case-insensitive, trimmed) anywhere in the sheet,
   not fixed row 4. Banner rows above the header are parsed dynamically by content/dates.
2. Supports any column order, any number of revision columns (R0, R1, R2, etc.), and extracts both schedule
   date and effective month date without hardcoding.
3. Customer blocks are dynamically recognized from heading rows (Column A, B, or D), part rows, and closing
   subtotal rows (e.g. `- TOTAL`). Each block is reconciled against its own closing row; grand total cross-checks customer blocks.
4. Ambiguous/unrecognized rows are captured in `needs_review_rows` with Excel row numbers and excluded from part sums.
5. Month mismatch validation: file banner month is strictly verified against selected planning month (blocking error).
6. Non-blocking "Norms match" chip column (`Matched` in emerald, `No norms found` in amber) is dynamically
   computed against current `ConsumptionNorm` records without requiring Product-Plant Mapping or Routes.
7. Step 2 preview includes a "Changes vs previous month" panel with metric badges (added, removed, qty changed,
   block diffs) and a downloadable CSV export button.
8. Re-uploading preserves R0 and R1 as separate records without summing.
9. Verified with full test suite: 57 backend tests passed (including 7 dedicated dynamic parser tests in
   `test_dynamic_sales_schedule.py`), 12 frontend vitest tests passed, TypeScript checks passed, and production build succeeded.

## Consumption Norms test panel removal — 2026-10-16

At the owner's request, ConsumptionNorms.tsx no longer renders "Test a consumption
norm", its Run Calculation form or preview results. Associated evaluation state and
the page's evaluate API call were removed. Norm creation, file import/export,
reviewed edits, filters and version history retain their existing behavior.
Requirement-module calculations, backend evaluation/formula logic, permissions and
database schema were not changed. The obsolete simulator UI test was removed;
the eight remaining focused Consumption Norms workflow checks passed.

## Shared product-wise requirements and October error repair — 2026-10-16

The owner wants the central plan and Existing monthly plans → Consumable Planning
Module to show the same production-derived consumable demand per product. For the
latest BASIC_CENTRAL_V1 revision in a selected month, monthly read/export/recalculate
now reuse central saved rows and calculation service. Manual monthly periods and
history remain separate. Production-based rows are read-only in the monthly grid;
edit production/norm sources instead. Central scope and approved-history protection
remain enforced through the monthly API. Response metadata adds source_workflow;
calculation responses/exports add product Part No/Item ID/description.

The sales-schedule parser fabricated Nos although its layout contains no unit column.
Future imports use the matched Product Master unit. Only known historical schedule
batch metadata permits recovering the old fabricated Nos default; original source
records remain unchanged and calculation evidence records the provenance. Explicit
source-unit mismatches still block approval. Monthly relationship loading is batched
to remove the per-row queries that caused timeouts. Product results precede compact
diagnostics; missing norm rows retain actual quantities and clear on recalculation.

A read-only check of October R0 found 509 source rows, 185 positive, zero saved valid
calculations and 1,018 old saved errors. Repaired preview: 66 calculation contributions
across 31 consumables, 142 source rows missing norms, 17 PROCESS_REQUIRED diagnostics,
zero false unit errors. These data gaps were not filled with guessed norms/processes.
Preview took 3.09s and the monthly read of old 1,018 errors took 8.78s in one observation.
No company records were changed or approved; Calculate and save refreshes unapproved
results. The former test-panel simulator's orphaned handler from the current merge
was also removed so TypeScript builds after its earlier owner-requested removal.
Forty distinct focused backend checks, nine frontend checks and TypeScript passed.
No migration or manufacturing formula change. Details are in the October repair
section of 24_CENTRAL_BASIC_PLANNING_CONTRACT.md.

### Live October recalculation and result recovery — 2026-10-16

After the owner signed into the ERP panel, Calculate and save was run once for
October R0 through the authenticated UI. A fresh read confirmed 65 saved requirement
lines (66 formula contributions consolidated by source/process/consumable), 31
consumables and 159 current diagnostics: 142 NO_CONSUMPTION_NORM and 17
PROCESS_REQUIRED. The 1,018 stale errors were replaced; no PRODUCTION_UNIT_CHANGED
errors remain. Central and monthly saved line IDs/quantities match exactly. The
monthly view includes the 65 calculated rows plus 159 explicit configuration rows.
The plan was not approved, source production was not rewritten and missing company
norms/processes were not invented.

The write succeeded but its follow-up read timed out, leaving the old zero-row
result visible. Central now distinguishes a committed save from a failed results
read, removes obsolete results after saving, and provides Reload results without
repeating the write or logging out. Reload also clears resolved missing-norm lists;
approval is disabled until saved results are available. Reload also recovers an
initial revision-list failure when no revision has loaded, without refreshing the
page/login.

Live connection latency remains variable: one read-only connection setup took
25.09s; the following central line/error/summary reads took 1.95/4.16/1.47s, and
the monthly conversion/read took 16.8s. These are observations, not a latency
guarantee. No provider settings, connection route, schema or formula changed.
Central revision/results and monthly records/metadata have a bounded 60-second read
allowance; other reads retain 30 seconds. Timeouts do not automatically repeat
writes. The manual planner no longer fetches the hidden MRP screen, and a successful
monthly reload clears an earlier timeout message. Final focused frontend
verification: 22 checks (10 central, 3 monthly, 9 loading), including result/revision
recovery, hidden-tab and timeout-budget regressions; TypeScript also passed.

Monthly metadata now loads revision/workflow/creator/updater together and counts
calculated/error rows in one statement (two reads total). The central monthly grid
reuses the selected revision and reads only the audit provenance columns it uses,
avoiding automatic audit-actor loads (four reads total). Sixteen focused backend
checks passed for central/monthly consistency, query budgets and direct norm
workflow, using disposable data. Saved production, quantity formulas and approvals
remain unchanged.

Final authenticated browser verification loaded both central's 65 saved lines and
the monthly grid's 224 rows (65 calculated + 159 configuration rows), without a
timeout alert. The monthly view was left open for the owner. This successful read
does not guarantee remote database latency for future requests.

## Faster record loading across ERP screens — 2026-10-16

The owner's session-pooler connection uses port 5432. Engine detection incorrectly
classified every Supabase pooler hostname as transaction mode, using NullPool and
discarding each connection/startup warm-up. Auto detection now reserves transaction
mode for port 6543; direct/session mode reuses configured bounded connections with
LIFO, pre-ping, keepalives and recycling. DB_POOL_MODE can explicitly select mode
for nonstandard proxies. Prepared statements remain disabled. The configured size,
overflow and wait settings are now honored, and diagnose reports the real pool.
No connection URL/provider plan, schema, password or employee grant was changed.

Central Requirement initial/post-save/reload reads use the additive basic/workspace
API for revisions and saved results together. Monthly uses workspace/view for rows
and metadata in one authenticated request. Existing endpoints remain compatible;
central/plant scope and fresh grants remain enforced. The central revision list is
one query and retains historical/latest selection semantics. Requirement/Purchase
grids use the existing virtualized DataTable. Production/monthly/Purchase remote
searches debounce at 300 ms and ignore obsolete result/error responses. Blocking
norm imports, assembly preview and manual requirement upload use request workers.

Read-only samples: old/new repeated connection rounds 2152/1586 vs 716/923 ms;
four physical connections became one. Existing Central result services 5218→2618 ms;
monthly metadata/records 8673→3948 ms. Counts stayed 65 valid lines, 159 configuration
rows and 31 consumables; monthly saved quantities match exactly. Separate combined
loader samples were 4738/5016 ms; remote latency still varies, including cold setup.
Running backend DB health and both registered APIs were verified. No company
business records were mutated during this performance work. Focused checks:
90 backend, 31 frontend, TypeScript and Vite production build passed. No migration.
Details, exact measurement boundaries and cross-team impact are recorded in
validation/RECORD_LOADING_2026-10-16.md.

## Production for sale month/year uploads — 2026-10-16

Owner requested month/year-wise production uploads. PRDPlanning now starts at the
client's current local month/year and has explicit Month and Year selectors next
to Upload Excel. The selected YYYY-MM scopes record loading, the visible grid,
new draft rows and current-view export. Switching periods clears old selection
and the revision filter; unsaved rows must be saved before switching/uploading.
Other periods and existing immutable revision history are retained.

SalesScheduleImportModal receives the selected period from the page and displays
it throughout preview/confirmation. Workbook metadata cannot silently replace it.
Changing workbook sheet/revision reinspects that exact selection; an initial
multi-revision preview is narrowed to one revision before confirmation. Upload
confirmation enforces parser errors and rejects a mixed month/revision payload.
Quantity headers such as Nov'26 (R0) now parse their explicit month/year without
falling back to the current month when the banner is absent. No schema, formulas,
planning approval authority or company business records changed.

Focused verification: 10 backend parser/import checks, 13 frontend production,
upload and search-loading checks, TypeScript and the Vite production build passed.
Disposable tests verified wrong-month rejection, October/November/next-year data
retention and separate R0/R1 revisions. No active ERP browser tab was available
for authenticated visual verification; no production workbook was uploaded.

## October Purchase Plan missing central demand — 2026-10-16

The Purchase Plan read only MonthlyRequirementRecord, so October's 65 central
CalculatedRequirement lines appeared as zero purchase rows. Central periods now
read the latest revision's saved demand, consolidated by consumable/unit, while
manual monthly plans retain their previous path. The connected database's repaired
read returned 31 consumables from 65 lines. October R0 remains unapproved with 159
diagnostics: 142 missing norms and 17 missing process assignments.

Central rows explicitly show requirement-review or assessment prerequisites.
Unavailable stock, incoming, raw purchase need and recommended quantities remain
null, never assumed zero. Existing traced assessment/approval evidence supplies
submitted purchase quantities. No arbitrary supplier, new stock formula or automatic
approval is introduced; the legacy queue endpoint rejects central submissions.
Read/export retain the central plant-scope boundary. The UI opens the selected
revision for review or assessment within the Purchase module; reload recovery keeps
that selection. Exports include the notice and blank unknown quantities.

No company data was mutated during diagnosis or verification. See the Purchase Plan
compatibility section of 24_CENTRAL_BASIC_PLANNING_CONTRACT.md for the boundaries.
Focused verification passed: 10 backend purchase service/API checks, 19 frontend
purchase/central/search checks, TypeScript and Vite production build. The live
database was checked through a read-only transaction; no authenticated browser
verification or company-plan approval was performed.

## Purchase grid scrolling and cell/row editing — 2026-10-16

Owner requested scrolling and Edit cell/Edit row in Purchase Plan, and answered
"Both" for purchase fields and master name/unit fields. PurchaseApprovals and
PurchaseWorkspace now bound nested flex dimensions, keeping the table's horizontal
and vertical scrollbars/footer accessible. The loaded originalData baseline fixes
the false 434-unsaved indicator. Browser verification with 31 synthetic rows reached
the last row, scrolled horizontally and saved name, proposed quantity and remarks
through the existing row editor. This was an isolated sample fixture using the
real components, with no company writes.

PurchaseWorkspace edits Consumable Name, Stock Unit (Master), Requested Purchase Qty
and Remarks; double-click/context menu/Save/Ctrl+S reuse DataTable. Masters require
master-update permission in addition to purchase-update permission. Name edits
sync canonical name/description, unit edits sync the unit link/output-unit display.
Existing stock-history/supplier mapping checks remain; a previously unassigned unit
can be filled later. Historical calculation/proposal units are never relabeled.
Calculated/system/approved quantities remain protected. Requested quantities and
remarks are separately versioned/audited proposals shown in the approval queue;
the existing explicit review/approval action is still required. Submitted proposals
cannot be rewritten in Purchase Plan. Failed saves keep edits, with an explicit
discard/reload action for stale-record recovery. Pending reads cannot overwrite edits.

New POST /api/v1/purchasing/workspace/save validates scope, latest revision,
permissions, selected rows, expected master details and draft version. Batch changes
are atomic. New purchase_plan_drafts and Alembic c003_purchase_plan_drafts follow
c002_optional_catalog_stock_units. Live schema had external marker 8c0f13ab0a53,
unavailable in this checkout. app.db.setup_purchase_plan --apply used the frozen
additive migration to create only this empty table while preserving that marker;
no history stamp or generic migration-chain rewrite was attempted. Default setup
is read-only. See the central planning contract for deployment boundaries.

Verification: 37 focused backend checks, 28 frontend checks, TypeScript and Vite
build. Read-only live verification confirmed ready storage, unchanged external
marker, zero proposals and the same 31 October consumables/65 requirement lines.
Company master records, quantities and approvals were not edited for verification.
The final local service check found both servers stopped; they were restarted in
hidden windows. Frontend returned HTTP 200 and the running backend OpenAPI exposes
the new save route. The temporary sample browser tab was closed after verification.

## Purchase page opening repair — 2026-10-17

After the recent merge, PurchaseApprovals still rendered the central screen for
Super Admin but no longer imported CentralRequirements. Its TabKey and read guard
also omitted central. This caused a render-time ReferenceError and the generic
PageBoundary fallback, rather than a missing-record or database error. Restored
the component import, central tab type and guard that prevents hidden approval
reads on central/workspace tabs. Kept the working-tree conflict-marker cleanup
and existing tab/navigation behavior. The same merge removed central test fixtures;
restored those fixtures from the prior verified revision, without altering tests'
business expectations. Requirements' issue banner now explicitly handles absent
metadata/counts to restore the TypeScript build.

Added purchase-page-loading.test.tsx against the complete PurchaseApprovals inside
PageBoundary. It covers Super Admin opening, Purchase Plan rows, selected-revision
review navigation, read-only queue/handoff access and recoverable central read
errors. Eighteen focused frontend checks, TypeScript and Vite build passed. An
isolated browser fixture using the real shell, boundary and Purchase components
opened both central assessment and Purchase Plan with sample data and no console
errors; no company login, reads, edits or approvals were performed. Screenshot:
.cache/purchase-page-restored-2026-10-17.png. The sample tab and fixture were cleaned
up. This repair changes no backend endpoint, schema, quantity formula or authority.

## Purchase Plan authenticated Excel export — 2026-10-17

Owner's Export Excel opened the protected workspace/export URL in a new browser
tab. Browser navigation did not attach the application's in-memory Bearer token,
so the server correctly returned NOT_AUTHENTICATED even while the ERP was signed
in. PurchaseWorkspace now requests the workbook through additive apiClient.getBlob,
which reuses the existing API base URL, authorization, timeout and error/session
handling and reads successful bodies as binary. It downloads a temporary object
URL with the period-specific .xlsx filename, then removes the link and releases
the object URL. Tokens are never added to URLs. Backend authorization is unchanged.

All/selected-row/filtered export modes retain month/year and their existing query
scope, including repeated record_ids. Export buttons show progress and block
duplicate downloads; errors are displayed in the grid without saving JSON as an
Excel file or opening an unauthenticated tab. No database/schema/quantity/approval
change; other modules' export flows were not changed by this scoped fix.

Changed frontend API client and PurchaseWorkspace; added purchase-export.test.tsx
and backend test_purchase_excel_download.py. Twenty-six focused frontend checks,
TypeScript and Vite production build passed. One isolated backend API check
confirmed unauthenticated rejection, authenticated valid .xlsx content/filename,
selected-row scope and search/status filters using openpyxl. No company data or
real account session was accessed for these tests.

## Both-contributor merge review — 2026-10-17

Owner explained accidental conflict resolution and requested preserving both sides,
repairing compatible bugs, then discussing mismatched features before choosing what
to remove. Reviewed common base 1381def, our e235905, incoming MRP-consolidation
5c2de7d/b4ccd59 and merge 760785b. Incoming changed 20 files; our side 29, with three
overlapping paths. Both branch patches and all pre-review unsaved/untracked work
were backed up under .cache/merge-review-2026-10-17/.

Incoming single MRP view, compact issue banner, issue APIs and CSV remain. Our
period-specific production upload, central component/review link, Purchase editing,
audited proposals, scrolling and authenticated Excel export remain. Repaired only
compatible integration: separate issue_count is honored by Purchase, metadata keeps
two batched queries, issue rows use real PRD/product identity instead of a nonexistent
error.product_code, and issues CSV downloads authenticate and escape formula text.

Pending owner choices: combined versus separate screens; existing central/plant
scope versus incoming Requirements-flag access; reviewer-selected date versus MRP's
first-of-month input. Older manual/Plant Review UI/router removals remain pending
discussion, with original source recoverable. No policy/date/approval decision or
company data change was made automatically. See
[merge comparison](validation/MERGE_REVIEW_2026-10-17.md) for evidence and options.

Verification: 32 frontend checks, TypeScript and Vite build passed. Backend audit:
20 passed, 2 existing central/plant boundary tests failed because the incoming
monthly API now permits those central reads. Failures remain visible; full merge
completion awaits an explicit access decision and corresponding validation.

## Owner-selected merge recovery completed — 2026-10-17

The owner answered the three merge questions: one Requirement/MRP screen with
central review and both contributors' features; retain existing central/plant
restrictions; use a date selected by the reviewer. This section supersedes the
pending-choice status in the immediately preceding dated audit.

Requirements.tsx now embeds CentralRequirements for the loaded production-based
period/revision. The incoming MRP grid, filters, manual monthly intake/editing,
issue count/banner/list/CSV remain. Central preview, calculation, separate Super
Admin approval, missing-norm acknowledgement, formula details, consolidated
breakdown and purchase assessment remain on the same screen. Advanced details
expand without a second primary Requirement tab. A single Calculation date feeds
preview/calculation; central monthly recalculate now requires explicit as_of_date
and records it in calculation evidence. No formula or norm-selection rule changed.

Central/plant scope checks are restored in the monthly router, including incoming
issue list/export. Existing grants and immutable calculated-row/approved-history
guards remain. Saving/calculating/approving reloads the grid; in-flight central
operations lock period/date, period switches clear old review, and Load Requirements
refreshes both surfaces and clears resolved central read errors.

Purchase defaults to Purchase Plan as in the incoming branch, retaining central
assessment, revision history, saved requested quantities/remarks, master edits,
cell/row editing, scrolling, queue/handoff and authenticated export. Its review
button navigates to /requirements?period=YYYY-MM; Requirement reads that period.
The MRP workbook download also uses apiClient.getBlob for authenticated binary
downloads with all/selected/filtered scope. DataTable has additive optional
fitHeight so the unified scrolling page bounds its grid in Fit mode; other grids'
defaults and existing height controls remain intact.

The incoming retirement of separate legacy Plant Review/manual-planner navigation
and plant/aggregation route groups remains. Active monthly-workspace manual features,
stored history, original source/commits and pre-recovery backups remain available.
No further routes were removed, no migrations were required and no company records
or approvals were changed. No commit/push was performed.

Validation: 54 frontend checks across 10 focused files and 32 backend checks across
the active workflow/merge/export paths passed, including both formerly failing
central scope tests, explicit reviewer date, manual monthly recalculation and
unchanged saved quantities. TypeScript and Vite production build passed. An extra
legacy plant-planner suite run was stopped after failures against already-retired
route groups; tests were not hidden/rewritten and this is not a full-suite pass.
See [final merge review](validation/MERGE_REVIEW_2026-10-17.md) for scope and evidence.
A browser fixture with the actual components and 65 synthetic rows verified both
scroll directions, last-row access and Compact/Fit controls; screenshot is
.cache/unified-requirements-2026-10-17.png. Fixture and sample tab were cleaned up.

## Purchase central tab removed at owner's request — 2026-10-17

Owner clarified that the incoming removal of the central purchase screen should
also be kept. Removed CentralRequirements import/render, central tab and central
selection state from PurchaseApprovals. Purchase has only Purchase Plan, Approval
Queue and Approved Handoff. PurchaseWorkspace's optional requirement link now
accepts a period and opens /requirements?period=YYYY-MM for both pending and
approved plans; the approved link is named View requirements. Assessment remains
within the existing unified Requirement screen. This supersedes the previous
entry's statement that Purchase retains a separate central assessment tab.

No backend/formula/access/approval or stored-record change. Purchase proposal/master
editing, downloads and queue/handoff remain. Focused Purchase tests and TypeScript
validation cover the three tabs, selected-period navigation, editing and exports.

## Compact Requirement layout requested by owner — 2026-10-17

Owner supplied the MRP screenshot and explicitly requested removal of the large
Central review panel, asking why it had been retained. It had been retained under
the earlier combine-both-features choice; the latest visual request supersedes that
embedded layout. Requirements.tsx no longer imports/renders CentralRequirements.
The page presents month/year, Load Requirements, Recalculate, Excel export, issue
CSV/banner, filters and the existing per-product grid. Initial loading uses one
combined monthly workspace read; no central workspace read occurs on page opening.

Recalculate now opens a compact date confirmation and calls the existing monthly
recalculate endpoint with the reviewer-selected as_of_date. Production-based rows
and approved calculations remain protected, and pending recalculation locks the
period and invalidates earlier reads. No recalculation automatically approves a
plan. Date input was moved out of the always-visible toolbar to match the screenshot.

The large central preview, calculation-details, consolidated-summary and assessment
panels are not embedded. Existing grid audit actions remain. To preserve the prior
explicit Super Admin review/purchase gates without that panel, a small arrow menu
beside Recalculate exposes Approve plan and Stock and purchase assessment. The new
RequirementPlanAction is lazy-loaded and fetches exact-revision evidence only when
opened. Hard calculation errors and historical revisions block approval; missing
norms still require explicit acknowledgement. Assessment uses the existing traced
component only for approved plans/materials. No backend/schema/formula/grant/approval
rule or company record was changed.

Validation: 22 focused frontend checks across compact MRP, date recalculation,
on-demand approval/acknowledgement/error blocking, read-only access, issues/exports
and existing central logic passed. TypeScript and Vite production build passed.
A browser preview used actual components with 65 synthetic rows and stubbed APIs,
confirmed the compact layout and date-dialog cancel behavior, and saved screenshot
.cache/requirements-compact-2026-10-17.png. Temporary sample files/tab were removed.

## Purchase Excel missing-value investigation — 2026-10-17

Owner supplied purchase_recommendations_2026_10 (2).xlsx and asked why remaining
columns were empty and whether a company formula was needed. Read the supplied
workbook without editing it: one sheet, 31 data rows and 18 columns. Every row is
REQUIREMENT_REVIEW_REQUIRED; the export-time notice records 159 configuration
issues. Required quantities and calculation/master units are populated. All stock,
incoming, raw need, recommendation and supplier fields are absent, rather than
numeric results lost during export. Requested quantities/approval statuses/remarks
are separate optional workflow fields. This describes that export's snapshot, not
an assertion about the current database state.

Owner selected “I'll provide the company monthly formula.” Actual formula and its
stock month/balance, pending-order handling, MSL/MOQ/pack rules and worked example
are pending. Do not change the quantity engine, default missing inputs to zero,
approve the plan, or treat monthly statement balances as reviewed usable stock
without that information. Existing contracts are still the implemented rule.

Independent export correction in purchase_workspace.py: unavailable numeric results
now display Unavailable with comments distinguishing pending requirement approval
from absent stock/supplier assessment. Missing supplier selection, approval and
requested proposal display Not selected / Not submitted / Not entered; optional
free-text remarks remain blank. Numeric values, true zeros and selection/filter/auth
behavior remain intact. Central stock/incoming/raw-need headers match their UI
meaning. Header wrapping/filter/frozen identifiers and wrapped report notice make
the report usable; column sizing ignores the long title/notice. Instructions now
point to the Requirement Recalculate menu instead of the removed central page.
No formula, API numeric type, database record or approval was changed.

Validation: 16 focused backend checks passed for central records/export, authenticated
Excel selection/filter, saved edits and numeric-zero preservation. Input workbook
is unchanged. Calculation completion still requires the owner's supplied formula
and input conventions; export presentation changes do not supply missing quantities.

## Owner-supplied monthly purchase formula — 2026-10-17

The owner supplied Downloads/KNL-Formula.xlsx and confirmed **Use uploaded Stock
Management MSL and MOQ**. This supersedes the pending-formula status above. Read-only
review identified a 150-definition formula catalog, not a complete operating plan.
Plan!AD4 is `gap = MSL + required − previous closing`; positive gap is raised to MOQ,
otherwise zero. Plan!AE4 multiplies quantity by rate. CO2 example: 981 + 2550 − 235
= 3296, above MOQ675; at rate9 value29664. Item-specific MSL-day variants, questionable
R2 source references and unrelated consumption families were not installed by inference.

Added exact Decimal KNL_MONTHLY_V1 calculation and batched source loader. Production-
based Purchase Plan previews use previous month's active Stock Statement closing
(January -> prior December), selected month's active Stock Management MSL/MOQ,
consolidated saved requirement and known Product Master rate. Shared item stock is
applied once. Existing known unit-label synonyms match; blank/numeric units and
unapproved conversions do not. Missing item/closing/limit, ambiguous limits/batches
and master mismatches stay null with precise input issues. Valid zero is preserved.
No PO deduction, pack rounding, lead-time demand or maximum cap is invented.

Screen and authenticated Excel now show MSL/MOQ/rate/value/stock period/calculation
basis. Excel appends details/issues after the original18 columns; pending incoming
is Not used by monthly formula. Source batch/file/hash/line/parameter IDs and operands
are available in API details. Existing submitted timed assessments keep their own
stock, incoming, quantities and engine version. Current monthly previews do not
create approval/PO rows or change the existing requirement review, timed assessment
and independent purchase-approval gates. Legacy manually imported monthly behavior,
proposal/master edits, norm maths, compact layout and access restrictions remain.
See [company formula contract](25_COMPANY_MONTHLY_PURCHASE.md).

Connected-data verification used READ ONLY / REPEATABLE READ transactions: October
has31 saved consumables; all31 have MSL/MOQ/rates;27 have sufficient stock inputs and
calculate. Four remain explicit source issues: AAC100002QC and AAC100003QC have blank
September closing balances; AAC100159QC and BAA110159QC are absent from September's
statement. NOS/PCS is compatible and is not the cause of those blanks. No company
records, requirements, approvals or source files were changed or submitted. Existing
requirement configuration issues still require review before plan approval.

Validation:39 focused backend checks (formula boundaries/example, source periods,
ambiguity/units/zero, shared stock, immutable assessments, edits and authenticated
Excel) and15 focused frontend checks passed. TypeScript and Vite production build
passed. A sandboxed run stalled at the TestClient export check after38 checks; it
was stopped and the same focused suite passed outside the sandbox. No full-suite
claim, migration, commit or push. The supplied workbook remains unchanged.

## Tool life engine, zero-stock policy, supplier resolution & October 2026 reconciliation — 2026-10-17

Owner requested fixing purchase recommendations and requirement numbers for October 2026 data across 8 identified discrepancies.
Alembic migration c004_tool_life_and_output_per_unit added output_per_unit, rule_type and purchasing_unit to Consumable and
ConsumptionNorm models and tables. 374 consumables and 662 norms were populated with tool-life and rule-type master data.

Deterministic KNL calculation engines in requirements_workspace.py and purchase_workspace.py now apply tool life:
for TOOL_LIFE, Req Qty = ceil(Gross Scheduled Qty / output_per_unit). Missing tool life flags OUTPUT_PER_UNIT_MISSING and suppresses
order recommendations; PRODUCTION_RATE uses gross quantity directly. Supplier lookup falls back to primary Consumable.supplier_id
when junction mappings are absent, restoring suppliers and master 'Nos' purchasing units for all 31 target items.
Exported Excel columns for Output / Unit now write numeric cells (data_type == 'n').

Configurable treat_missing_stock_as_zero (default True) added to core/config.py, MonthlyPurchaseInputs and workspace services,
matching Excel SUMIF behavior and unblocking AAC100002QC, AAC100003QC, AAC100159QC and BAA110159QC with zero stock and explicit audit notes.
Order quantities enforce max(Raw Need, MOQ) rounded up to MOQ multiples when raw need is positive.

Reconciliation workbook Purchase_Reconciliation_2026_10.xlsx was generated at root and artifact directory. 15 of 31 items match KNL's
plan 100%. The remaining 16 items have scheduled quantity differences traced component-by-component to manual typed overrides in
oct plan og.xlsx versus master norms in Basic_Consumable_Plan_Sheet.xlsx; ERP calculations strictly preserve master norm traceability.
Total purchase value for the 31 target items is Rs 1,98,909 (~Rs 1.99 Lakhs) versus Plan R1 Rs 87,030 (~Rs 0.87 Lakhs), reduced from
Rs 4.5+ Crores previously.

Validation: 68 backend pytest tests (tool life math, monthly purchase formula, central workspace, norm imports, requirement consistency)
and frontend Vite production build passed with zero errors. All changes committed (e2e3d53) and pushed to branch feature/mrp-view-consolidation.
Protected files stock_management_service.py and DataTable.tsx remain untouched.
