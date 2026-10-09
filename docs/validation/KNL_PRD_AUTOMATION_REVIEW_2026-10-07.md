# KNL PRD-only upload workflow: review and company questions

Review date: 7 October 2026. Requested by Munees.
Repository reviewed: `develop`, commit `95a5d83`.
Status: engineering review and business clarification; not production acceptance.

## Requested operating model

The planner manually uploads the `Prd. Order` production schedule. The application
then validates a specific period/revision, resolves approved product/plant/process
mappings, calculates consumable requirements, obtains required human confirmations,
uses current external stock and confirmed supply, recommends purchases, supports
approval and PO creation, imports accepted receipts, and updates reports and alerts.

One-time migration of masters, mappings and approved norms is still required.
Exceptional maintenance/trial/department requests and purchase approvals need their
agreed source or human workflow. A production schedule cannot supply changing stock,
inspection results, supplier promises or unplanned demand by itself.

Supabase stores this application's data. It does not automatically connect this
application to KNL's existing ERP. PRD can be the only recurring manual file upload
only if the other required sources arrive through an approved automated connector
or automatic delivery of ERP export files. If neither is available, another source
entry process is necessary, and the strict PRD-only upload objective remains blocked.

## Evidence and review limits

Inspected current frontend routes and API calls; backend PRD, requirement, inventory,
projection, reorder, recommendation, approval, PO, GRN, report and alert paths;
authentication/permission paths; project contracts; migration heads; and the source
workbook structure and representative formula dependencies.

Workbook: `1.Consumable plan- Aug '26 REV-1.xlsx`, read from Munees's Downloads folder.
No workbook or operational database data was changed. This was not a production
deployment test, penetration test, complete recalculation of every workbook cell,
or proof of operational PostgreSQL concurrency/restore behavior.

Current verification:

- Backend: `python -m pytest app/tests -q`: 11 passed, 5 deprecation warnings.
- Frontend: Vitest: 6 test files, 43 tests passed; one navigation-not-implemented message.
- TypeScript build: passed. Vite production bundle: passed.
- Local migration graph: one head, `0019_prd_workspace`. This does not establish
  which migration is applied to the hosted database; no database migration was run.
- The normal npm launcher failed because its configured npm-cli.js was missing.
  The equivalent installed TypeScript/Vitest/Vite tools ran with bundled Node.
- These tests do not establish company-approved formula parity. The current backend
  suite contains two workspace test files, not comprehensive domain acceptance tests.

## Workbook compatibility

`Prd. Order!A1:M6` has four header rows. Row 1 carries month labels, row 2 schedule
issue dates, row 3 planning months, and row 4 identifiers and R0/R1 revisions.
Column B is Part No.; C is Item ID; D is description. E is August R1 and F is
August R0. They must not be added together or selected by a generic Qty header.
The first product has R1 zero and R0 200, illustrating why zero, blank and revision
selection need explicit semantics.

Executed the current header-detection statements against these source rows without
database writes. The actual matches were only `product_code: 1` and `description: 3`.
No planned-quantity column was recognized. The subsequent importer code substitutes
zero when that column is missing. This is a confirmed format incompatibility.

`Plan!A2:BW4` combines supplier/material references, stock statements, GRNs, plant
requests and calculation outputs. `Plan!AT4:BG4` aggregates department/plant demand;
this demand is not universally derived from PRD. Examples of literal quantities:
`Plant II!G5:G6` and `Plant V!G3:G6`. Scanned quantity columns also contain literal
values in Tool Room, PMD, NPD and HRD. Each needs a known business origin.

The workbook contains multiple MSL/reorder formulations (`Plan!V4`, `BO4`, `BR4`,
`BT4`) and working-day/MSL-day inputs (`X1`, `U3`). These must be reconciled with
KNL's chosen policy rather than copied as universal defaults. For example, BO4
adds daily quantity to a hold-days value; its intended units/formula need review.

The workbook also has a sheet whose declared extent is 1,048,486 rows. Inspecting
every sheet by materializing every row is unsuitable for a PRD-only import. Read
the selected sheet with bounded parsing and explicit size/row limits.

## Current engineering findings

| ID | Finding and consequence | Required correction |
| --- | --- | --- |
| E01 | PRD/Requirements routes are now connected to workspace screens. Prior placeholder findings are superseded. | Review the data flow, not only page visibility. Administration remains a placeholder. |
| E02 | Production Mappings reads Product master. PRD workspace saves textual product codes into `PRDRecord` and does not register Product records. An uploaded row therefore does not automatically populate the product selector. | One-time product migration/synchronization and an explicit unknown-product review flow; preserve both external identifiers where required. |
| E03 | Actual PRD R0/R1 quantity columns are not recognized. Missing quantity becomes zero; missing plant/period/version receive guessed defaults. | Workbook-specific mapping, period/revision preview, strict validation and useful row errors; never guess a plant or turn an invalid quantity into zero. |
| E04 | Workspace PRD data is separate from canonical `PlanningVersion`/`PRDOrderItem`. Workspace requirement recalculation does not create the canonical calculated requirements used by plant confirmation and purchase traceability. | Integrate staging, validated promotion and calculation through existing authoritative services, with stable IDs and provenance. |
| E05 | `requirements_workspace.py` invents 5%/10% requirements and MSL 10/5 when mappings are absent. With mappings, it recognizes different rule names from the approved engine and defaults to factor 1. | Remove inferred production quantities and thresholds. Reuse the approved rule engine; missing configuration must remain an explicit blocker. |
| E06 | Workspace stock query sums historical snapshots. | Use the latest authoritative usable snapshot through the inventory service. Two observations of 100 and 80 must report 80, not 180. |
| E07 | Workspace pending supply sums ordered quantities without PO state, accepted receipts, cancellation or delivery-time qualification. | Reuse approved pending/projection services and reconciliation. Prevent PO/receipt double counting. |
| E08 | Workspace calculation includes all undeleted PRD rows, without choosing an active period/revision; norm selection is keyed only by process/material. | Enforce planning-version scope and approved product/plant/effective-date norm resolution. Preserve revision history. |
| E09 | PRD REPLACE soft-deletes all active workspace rows, with no period/revision scope; APPEND has no source import identity protection. | Define replacement semantics first, then implement scoped revisions and duplicate/retry protection. |
| E10 | Goods Receipts workspace imports/edits `GoodsReceiptRecord`; these do not execute the authoritative GRN import that updates PO fulfilment and stock evidence. | Connect the receiving view to approved external-GRN imports and show authoritative source linkage. Workspace saving is not stock posting. |
| E11 | Alerts use a fixed MSL of 100, a 20% approach band and a fixed 3-day PO warning window; absent stock is treated as zero. | Use effective approved MSL and configured alert policies; distinguish missing/stale data from shortage. Connect reorder alerts to the domain result. |
| E12 | Alert evaluation is exposed as an on-demand API. No automatic recurring evaluation or external source connector was found in the inspected app. | Add verified data refresh, calculation triggers, reliable retries, scheduled evaluation and freshness/error monitoring as needed. |
| E13 | Several master/production/requirements routes check login without explicit action permissions or plant scope. UI role rules and stored grants are separate; the dev seeder grants all permissions to every role. | Implement the approved backend permission/scope matrix, restricted provisioning and separate requester/reviewer accounts. Do not use demo grants as production policy. |
| E14 | Dashboard quantity totals aggregate across records without material/unit and selected-version grouping. | Use meaningful counts or material/unit/period-specific totals; do not add kg and pieces into one business quantity. |
| E15 | Company-approved numeric cases, full regression coverage and operational deployment/restore evidence are incomplete. | Restore/add business-critical tests and independently reconcile KNL examples; validate PostgreSQL transactions, deployments and recovery before release. |

Source locations: `frontend/src/App.tsx`, `frontend/src/features/mappings/ProductionMappings.tsx`,
`backend/app/services/prd_workspace.py`, `backend/app/services/requirements_workspace.py`,
`backend/app/services/requirements.py`, `backend/app/services/grn.py`,
`backend/app/services/alerts.py`, `backend/app/services/dashboard.py`,
`backend/app/modules/masters/router.py`, `backend/app/api/production.py`,
`backend/app/modules/requirements/requirements_workspace_router.py`, and
`backend/scripts/seed_dev_users.py`.

## Decisions already recorded: do not reopen without a requested change

- Company name KNL; one central consumable store.
- Existing ERP owns opening, reservations, warehouse posting, corrections and GRNs.
- Only accepted usable receipts and usable returns increase usable stock.
- Rejected receipt quantity remains pending for replacement.
- A PO is a commitment; an issue to a plant is not automatically actual consumption.
- Quantities support four decimal places; exact arithmetic is required.
- Missing business policy is not an invented default.
- Purchase recommendations preserve server-generated evidence; older approvals
  without that evidence require resubmission before PO creation.
- Owner-approved M5.1 development behavior already exists: explicit target at receipt,
  no purchase for raw quantity <= 0, MOQ followed by joint pack/multiple constraints,
  and a visible conflict when a maximum is exceeded. KNL numeric acceptance is still
  needed; do not describe this as already signed off by the company.

## KNL questionnaire

Answer Q01-Q06 first to establish the one-upload design. Other questions can be
resolved by phase, but each affected feature must have an answer before live use.
For each answer record the approving KNL person/role, effective date, example and
source document. `TBD` is acceptable and leaves the affected behavior unavailable.

| ID | Question for KNL | Why the answer is needed |
| --- | --- | --- |
| Q01 | What is the existing ERP product/vendor, and who can approve access? Can it provide an API, approved read-only feed, or automatically deliver stock, open-PO and GRN exports? Supply sample field layouts and frequency, without credentials. | PRD-only manual upload requires automatic external inputs. |
| Q02 | Will users upload a standalone Prd. Order sheet or the full workbook with that sheet selected? Is the shown multi-row layout stable? How are month and active revision selected? | Build the correct importer and preview. |
| Q03 | Does a revised schedule replace the entire month's plan, replace only listed products, or add changes? What do blank, zero, omitted and duplicate lines mean? What happens to already approved demand/issued POs after a revision? | Prevent duplicate demand and destructive replacement. |
| Q04 | Is Part No. or Item ID the authoritative product key? Can either repeat/change? Provide the product, plant, route/process and product-to-consumable mapping source. For a product made at multiple plants, who supplies the quantity split? Should unknown products wait for setup approval? | Correct product selection, plant allocation and master onboarding. |
| Q05 | For each consumable/category, what approved rule, parameters, unit and rounding generate its requirement? Provide applicable product/plant/process and effective dates. Which workbook formula wins where columns disagree? | Configure actual engineering rules instead of copying inconsistent cells. |
| Q06 | Where do literal quantities in Plant I-V, Tool Room, PMD, NPD, HRD, QAD and Sales originate? Classify each as production-derived, approved recurring quantity, historical-use rule, or manual exception. Who supplies and approves exceptions in the portal? | These values cannot all be inferred from PRD. |
| Q07 | Is demand needed monthly, weekly or on specific dates? Provide the source dates or an explicitly approved allocation method, work calendar and timezone. | Exact shortage/order dates cannot be inferred from a monthly total. |
| Q08 | Which existing-ERP field is usable stock and what exclusions does it already contain? Provide stable material/event/document IDs, stock-unit mapping and snapshot timestamps. How fresh must it be, and should stale data block recommendation or show a warning? | Preserve usable-stock meaning and source freshness. |
| Q09 | Which PO statuses count as confirmed incoming? What date means material is usable? How are partial receipts, cancellations, changed delivery promises and already fulfilled demand reconciled? | Avoid counting unavailable supply or deducting satisfied demand twice. |
| Q10 | Is MSL fixed per material or calculated by an approved formula? Which of the workbook's MSL/reorder columns is authoritative? Does exactly MSL trigger action or only below MSL? Who approves changes, with what effective date? | One consistent policy for projection, reorder and alerts. |
| Q11 | What sets target stock at receipt: explicit quantity, maximum stock or approved coverage rule? How are horizon and any maximum order/stock constraints defined? Supply one dated example. | A purchase quantity needs an explicit target. |
| Q12 | For each supplier/material, what are lead time, MOQ, mandatory pack size and order multiple, including units? Are lead-time days calendar or working days; does time run from PO issue to acceptance? What does each blank/zero mean? | Reliable supplier constraints without defaults. |
| Q13 | Confirm the current owner-approved constraint behavior using examples, including incompatible MOQ/pack/multiple/maximum cases. Should any terms be optional, and how is 'not applicable' recorded? | Obtain KNL acceptance of provisional development policy. |
| Q14 | How is a supplier selected: approved preferred supplier, buyer selection or a specified comparison rule? Are split orders and substitutions allowed? How are rates, currency, quote validity and pricing approval recorded? | Automate only authorized sourcing decisions. |
| Q15 | Which materials allow fractions, which require whole pieces/packs, and which purchase-to-stock conversion factors are approved? At which calculation stage must rounding occur? | Prevent unit and quantity errors. |
| Q16 | What are the exact role/action/plant permissions? Who confirms plant demand, approves extras, changes norms/MSL, approves/modifies purchases, issues POs and manages accounts? Specify delegation, limits and any requester/reviewer separation. | Implement access and approval policy without guessing role authority. |
| Q17 | Does the new application issue the official PO or send an approved purchase request to the existing ERP? If it issues a PO, how does the existing ERP learn its number/line IDs so imported GRNs can match it? | Complete traceability across both systems. |
| Q18 | What are the policies for issued PO amendments/cancellation, over-receipts, inspection-pending material and corrected/reversed GRNs? | Current unsupported cases must stay blocked until their contracts are approved. |
| Q19 | Which alerts are needed: missing mapping/norm, stale source, below/near MSL, future breach, late ordering, delayed PO or pending approval? Define recipients, threshold, evaluation frequency, channels, reminders/escalation and resolution. | Replace fixed thresholds with useful agreed alerts. |
| Q20 | After a valid PRD upload, which stages should run automatically and where must a human confirm? May the system create a draft purchase request automatically? Human approval and PO issuance remain separate unless explicitly changed. | Define automation boundaries and triggers. |
| Q21 | Which Plan/Summary plan columns, department views and exports must match Excel? Is visual layout parity needed, or the same business outputs with a simpler screen? How should planned-versus-actual consumption be sourced and defined? | Establish the required outputs and acceptance boundary. |
| Q22 | Provide at least 10 signed numeric examples across real rule families, revisions, missing mappings, exactly/below MSL, incoming timing, MOQ/pack/multiple, partial/rejected receipts and no-order cases. Include inputs, dates, expected outputs and approver. | Independently prove formula/workflow parity; synthetic tests are insufficient. |
| Q23 | What are normal and peak product/material/PO counts, upload size, concurrent users and acceptable calculation time? | Set measurable performance tests and deployment sizing. |
| Q24 | Who owns hosting, backups, restore decisions and user support? What history must be migrated, retained and locked, what downtime/data-loss limits are acceptable, and who signs off cutover? | Establish operational readiness and recovery acceptance. |

Suggested response format:

```text
Question ID:
Answer (or TBD / Not applicable):
Approved by (KNL name and role):
Effective from:
Example with quantities, units and dates:
Supporting document/export/reference:
```

## Proposed implementation sequence

1. Correct misleading calculations and source aggregation; use the existing domain
   engines consistently across workspace screens, alerts and reports.
2. Migrate reviewed masters/mappings/norms once. Add usable setup screens and
   missing-configuration guidance; preserve external keys and approval history.
3. Build the real Prd. Order adapter with period/revision selection, staging,
   validation, idempotency and canonical planning-version promotion.
4. Connect calculation, plant confirmation, exceptions and final requirements.
5. Integrate the approved external stock/open-PO/GRN source with freshness checks,
   reconciliation, retries and failure visibility. No operational activation until
   source mapping is validated.
6. Connect projection, reorder, recommendation evidence, approval and PO handoff.
7. Add approved automated triggers, alert policies and Excel-compatible outputs.
8. Validate company examples, role denials, revision effects, concurrent receipts,
   rollback, representative workload, backup restore and cutover reconciliation.

Existing domain foundations can be reused. The immediate problem is inconsistent
integration and incomplete company configuration, not a need to invent another
calculation engine. Technical corrections do not require KNL to design the code;
the company questions concern inputs, business meaning and operating authority.
