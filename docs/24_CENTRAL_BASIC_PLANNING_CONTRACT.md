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
   formula/date/rounding → confirm. Check saved versions and the calculation preview.
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
