# Shared Requirement/Purchase merge review — 2026-10-17

The owner requested preserving both contributors' work, repairing compatible
integration bugs and discussing conflicting behavior before choosing what to remove.
The comparison was followed by the owner's explicit decisions below and their
implementation. The initial findings remain recorded for traceability.

## Final owner decisions and implementation

**Latest Requirement layout correction:** the owner then supplied the compact MRP
screenshot and requested removal of the embedded Central review panel. Requirement
now opens directly to the period toolbar/issues/grid, with Recalculate restored.
Reviewer-selected date entry is in its confirmation dialog. Existing approval and
assessment actions are on demand in the small toolbar arrow menu, preserving
Super Admin, hard-error, missing-norm acknowledgement and approved-plan safeguards.
There is one initial workspace read. No backend rule/quantity/approval record change.
22 focused frontend checks, TypeScript and build passed; synthetic browser proof is
`.cache/requirements-compact-2026-10-17.png`. This supersedes embedded-panel retention
described in the earlier resolution below.

**Follow-up correction:** the owner subsequently requested matching the friend's
removal of the central purchase tab. That tab/import/state is now removed from
Purchase. Its three tabs are Purchase Plan, Approval Queue and Approved Handoff;
requirement links for pending/approved periods go to the unified Requirement
screen. Assessment remains there. This supersedes separate-Purchase-tab retention
in the initial resolution described below. Existing Purchase edits and exports
are retained; no backend record, formula or access change was needed.

The owner chose **one Requirement/MRP screen with central review and both sets of
features**, **the existing central/plant restrictions**, and **a date selected by
the reviewer**. These choices are implemented; no decision remains pending among
the three questions asked.

- Requirement opens the incoming MRP view with its period selector, spreadsheet,
  filters, issue count/list/CSV, manual monthly intake and existing edit behavior.
  For production-based periods it embeds central matching, Calculate and save,
  separate Super Admin approval, formula details, missing-norm acknowledgement,
  consolidated material breakdown and purchase assessment. Advanced review details
  expand on the same page. Review follows the main grid's period and saved revision.
- One Calculation date input supplies central preview/calculation. The monthly
  compatibility recalculate API accepts `as_of_date` and requires it for central
  periods instead of silently using the first of the month. Existing formulas and
  norm matching are unchanged. The saved calculation evidence records that date.
- Central/plant restrictions are restored on monthly reads, exports, recalculate,
  and incoming issue-list/CSV routes. Existing feature grants are still checked.
- Calculation and approval refresh the main MRP grid. A pending central operation
  locks the period/date; changing period clears the previous review. Load Requirements
  retries both parts of the page and clears resolved central read errors.
- Purchase opens Purchase Plan directly, as in the incoming version. Its review
  link opens the unified Requirement screen for that period; its central assessment
  tab, historical revision selector, proposal/master-field edits, approval queue,
  handoff, scrolling and authenticated exports remain.
- MRP Excel export also uses authenticated binary downloads with period, selected
  rows and filters preserved. Fit mode is bounded on the scrolling Requirement
  page through an optional DataTable `fitHeight`; other grids retain their defaults.
  Compact, Standard, Large, custom resizing and fullscreen remain available.

The incoming retirement of separate legacy Plant Review/manual-planner navigation
and plant/aggregation route groups is retained. The active monthly workspace's
manual import/edit/recalculate paths and saved history are retained. Original
legacy source/commits/backups have not been deleted by this recovery.

## Verified history

| Reference | Meaning |
| --- | --- |
| `1381def` | Common starting point. |
| `e235905` | Our saved work before the merge, committed 17 October at 09:21 IST. |
| `5c2de7d` / `b4ccd59` | Incoming `feature/mrp-view-consolidation`, authored 16 October at 23:14 IST and merged through PR #34. |
| `760785b` | Combined merge on 17 October at 09:24 IST. |
| Working tree | Today's Purchase page/export repairs and this compatibility review. |

Our side changed 29 files and the incoming side changed 20. Three paths overlap:
PurchaseApprovals.tsx, CentralRequirements.tsx and central-basic-planning.test.tsx.
The incoming side removed CentralRequirements while our side updated it. Partial
resolution kept JSX references but removed the import/tab declaration and test
fixtures, causing the Purchase crash. Those wiring errors have already been repaired.
Choosing one entire side again would discard useful independent changes.

Source patches for both sides, the pre-review working patch and copies of all
then-untracked tests are saved under `.cache/merge-review-2026-10-17/`. Original
commits remain available in Git. No reset, whole-merge revert or repository push
was used for this review.

## What each change does

| Area | Our work | Incoming work | Current disposition |
| --- | --- | --- | --- |
| Requirement interface | Separate central review, manual monthly planner and MRP surfaces. | One MRP screen; removes central/manual navigation. | Owner selected one MRP page with central review/actions integrated; both sets of active features retained. |
| Issue reporting | Calculation diagnostics remain visible; Purchase warns about configuration issues. | Separate `issue_count`, compact issues banner, issue-list API and CSV. | Both retained. Fixed their count mismatch and the new CSV's runtime/authentication bugs. |
| Purchase | Central demand compatibility, explicit assessment, saved proposals/remarks, master-name/unit edits, row/cell edits, scrolling and review navigation. | Opens Purchase Plan directly and removes the central assessment tab with the central screen. | Opens Purchase Plan directly; central assessment and editing retained. Requirement review links to the combined page for the correct period. Queue and handoff remain. |
| Production input | Month/year selection, exact selected-period import and immutable revisions. | No changes to these files in this incoming commit. | Retained. |
| Faster loading | Batched metadata, combined reads, debounced searches and virtualized grids. | Splits valid-line and issue counts into separate reads. | Retained both count fields while recombining count retrieval, restoring two metadata queries. |
| Excel exports | Today's authenticated Purchase downloads with selected/all/filtered scope. | Adds Requirement issues CSV via a direct link. | Purchase export retained; issues CSV now uses the same authenticated binary client. |
| Older manual/plant workflows | Separate screens and backend routes for older monthly plans/plant confirmations. | Deletes old screen files, redirects Plant Review to Requirement and unregisters plant/aggregation route groups. | Separate legacy navigation/router retirement retained; active monthly intake and history preserved. Source remains recoverable. |
| Access | Central API and monthly compatibility view restrict plant-scoped users. | Monthly API relies on Requirements read/update grants and removes its central scope check. | Owner selected previous central/plant restrictions; restored, including the new issue routes. Both earlier failing boundary checks pass. |
| Calculation-date input | Central view sends a reviewer-selected effective date. | MRP recalculate sends the first day of the selected month. | One reviewer-selected date, passed and saved explicitly. No formula or norm-matching policy changed. |

Focus descriptions above are inferred from the actual code changes, rather than
assuming either contributor intended to remove the other person's work.

## Compatible repairs applied

1. Preserve incoming `record_count` as valid calculation lines and `issue_count`
   separately. Purchase now reads `issue_count` rather than deriving zero issues
   from the new valid-line count; no quantities or approvals are rewritten.
2. Fetch valid-line/issue counts in one database round trip, retaining the earlier
   loading optimization and both contributors' response fields.
3. Resolve issue identity through the actual PRD source/product relationships.
   RequirementCalculationError has no `product_code` attribute, which previously
   caused the incoming issues API/CSV to fail when errors existed.
4. Retain the incoming issues banner and download feature. Download CSV through
   the authenticated client, display retryable UI errors and preserve period/name.
   CSV text beginning with spreadsheet formula characters is escaped consistently
   with the existing export convention.

No schema migration, further endpoint removal, new formula, approval, source rewrite
or company record mutation was performed. Access and calculation-date changes follow
the owner's explicit choices; no authority was expanded.

## Original questions, subsequently answered above

1. **Screen layout:** one MRP screen with central review/approval/assessment actions
   integrated, or separate central/monthly surfaces. Recommendation: one main MRP
   surface with the required central actions preserved; keep old plan history
   recoverable, and decide separately whether older manual/plant workflows need
   active navigation again.
2. **Access:** preserve central/plant restrictions, or intentionally grant central
   reading/recalculation to users holding Requirements permissions. Recommendation:
   preserve existing restrictions unless company authority explicitly changes.
3. **Date input:** reviewer-selected date or the first day of the planning month.
   Recommendation: use one explicit reviewer-selected input consistently. Current
   central norm matching already has its own date handling; its rules are outside
   this comparison's automatic repairs.

## Initial verification before the owner answered

- Frontend: 32 checks passed across incoming MRP/issue behavior and our central,
  Purchase page, cell/row save, export and period-import behavior.
- Backend: 20 passed and **2 failed** in the focused merge audit. The failures are
  existing access-boundary checks, because the incoming monthly API returns 200
  where the previous central/plant contract requires 403. These tests were not
  deleted, skipped or rewritten to hide the policy difference.
- Both new issues APIs are covered with disposable data, including real CSV rows,
  period identity, permission grants, counts and Purchase notice compatibility.
- TypeScript and Vite production build passed.
- No live account/database mutations or authenticated browser changes were used.

## Final verification

- **54 frontend checks passed** across 10 focused files: unified Requirement,
  central planning, Purchase page/workspace/export, incoming issues, existing MRP,
  selected-period production import, record loading and stock-grid editing.
- **32 backend checks passed:** 23 merge/central/monthly-consistency/loading tests
  plus 9 active monthly-workspace and authenticated Purchase export tests. These
  cover both formerly failing central/plant boundary checks, the new issue routes,
  exact reviewer-date evidence, unchanged quantities, manual monthly edits/import/
  recalculation, counts, CSV safety and a readable Excel workbook.
- TypeScript and the production build passed. Existing dependency deprecation
  warnings remain; no test was weakened or skipped to hide a failure.
- An extra run of older plant-planner tests produced failures and was stopped.
  Those tests still target the incoming-retired `/api/v1/plans` and aggregation
  surfaces; an OpenAPI inspection confirms `/plans` is absent while the active
  `/requirements/workspace/view` is present. These tests/routes were not silently
  reactivated or altered. This is not a claim that the entire repository suite passes.
- A browser preview used the real shell and components with 65 sample rows and
  stubbed APIs. It verified review controls, separate page/grid scrolling, last-row
  access, right-side columns and Compact/Fit sizing. Screenshot:
  `.cache/unified-requirements-2026-10-17.png`. The temporary fixture/tab were removed.
- No company production, requirements, purchase quantities, approvals or account
  permissions were mutated. Changes are local and have not been committed/pushed.
