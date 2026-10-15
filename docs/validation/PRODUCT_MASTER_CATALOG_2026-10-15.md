# Product Master: undated catalog and explicit save — 2026-10-15

Owner: Munees. This correction supersedes the earlier month/year Product Master
workflow. Stock statement and stock management keep their existing period controls.

## Current flow

Product master → choose one of the three tabs → Bulk Import. There are no month or
year selectors. Existing active catalog rows appear immediately, including records
uploaded through the former monthly UI.

- Existing records display Saved. Save changes becomes available after editing.
- To replace a tab's data, Delete data requires a reason, reviewed token and
  confirmation. It deactivates that tab's active entries while retaining IDs,
  mappings, previous upload evidence and audit history. Other tabs are unaffected.
- Upload data reads the first worksheet and opens an unsaved preview. It performs
  no master/unit/supplier writes and creates no audit/period batch.
- Review the row counts, duplicate warnings and missing identifiers. Existing
  duplicate behavior is explicit: last source row per master identity wins.
- Save changes saves the upload even when no cell has been edited. It submits the
  original workbook with reviewed edits; the backend parses/validates it again and
  commits masters and audits atomically. Discard upload performs no persistence.
- Saved catalog edits use optimistic review tokens. IDs/mapped references remain
  protected. A newly staged upload permits reviewed unit labels to be corrected.
- Export Excel exports the current saved catalog with no artificial reporting date.

## Workbook count investigation

The supplied consumables workbook was inspected read-only with the bundled Python
runtime and reconciled independently against the actual backend parser:

- First worksheet: List of Consumables; title row 1, column headers row 2.
- Rows 3–475 contain 473 candidate rows, 471 with an Item ID.
- Rows 25 and 377 have descriptions but no Item ID, so they are reported as skipped.
- Three duplicate IDs occur at row pairs 49/318, 63/322 and 144/159.
- Correct unique master count: 471 − 3 = **468**.
- Cell A475 displays a cached serial 467 from `SUBTOTAL(103,$D$7:D475)`. That
  counter omits the first four identified material rows; it is not a unique count.
- The actual parser produces 468 preview rows and 174 rows with numeric
  Output/Unit values. Numbers such as 2000 cannot safely become stock-unit codes.
  These rows are flagged; a person must provide the actual unit labels. The preview
  supports cell edits and an explicit apply-to-unresolved-units action. No numeric
  output quantity is converted into a consumption norm or guessed unit.

The owner asked whether a PCS/KG column is needed. Add a separate Unit/UOM/Stock
Unit column in the same workbook. It takes precedence over Output/Unit. If that
explicit column is present, a blank unit stays unresolved instead of falling back
to a capacity or a guessed label. Keep numeric Output/Unit source values intact.

The supplied workbook was not overwritten. Blank unit cells retain the established
importer fallback; numeric unit labels are newly rejected on catalog save.

## Implementation and verification

New API family: `/api/v1/masters/product-master/{category}/workspace`:
GET current catalog, POST reviewed workbook + JSON review form, PATCH changed
fields, DELETE reviewed catalog; POST `/preview`, GET `/export`.
Explicit masters read/create/update/delete flags or Super Admin apply.

`MasterCatalog` audit entries retain source filename, workbook hash, import report
and row count. No new month/year batch is created. Former active monthly batches
are archived with audits on catalog corrections/deletion, preserving their contents.
Applied migrations and existing historical storage are retained. No new schema
migration or live company-data edit/deletion was required for this correction.

Focused checks: eight catalog backend cases plus ten retained-history/parser cases,
twelve Product Master UI cases, actual-file read-only count reconciliation, TypeScript
and production build. No unrelated full suites, commit or push were run.
