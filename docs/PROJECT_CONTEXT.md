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
| Consumption norms (/rules) | Norm version/effective dates/parameters and simulation; services/rules.py, domain/rules/engine.py and handlers |
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

