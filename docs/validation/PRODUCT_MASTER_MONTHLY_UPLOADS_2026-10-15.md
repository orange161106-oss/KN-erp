# Product Master monthly bulk workspace — 2026-10-15

Historical implementation record. Munees subsequently clarified that Product Master
must not use month/year uploads. The current workflow is documented in
[Product Master catalog](PRODUCT_MASTER_CATALOG_2026-10-15.md). Existing storage and
historical evidence described below are retained; the current UI uses the undated
catalog with preview followed by explicit Save changes.

Owner request: add month/year, Excel upload, selected-period deletion, Save changes
and Export Excel to Product Master only. Existing manual forms and planning logic
are preserved.

## User flow

1. Open Master data → Product master.
2. Choose List of Consumables, Consumable for Assemble, or List of Sales Parts.
3. Choose Bulk Import. If older/manual entries have no period, the workspace opens
   **Existing data — no month/year recorded**. Review the rows, choose Delete data,
   provide a reason and confirm. This affects only the selected Product Master tab.
4. Select the month/year, then upload the corresponding `.xlsx` workbook (first worksheet, existing
   header aliases supported). Upload commits the valid workbook atomically.
5. Double-click an editable description/value cell, finish the edit, and choose
   Save changes. IDs, referenced units and mapping keys are protected.
6. Export Excel downloads the saved selected-period data.
7. Delete data requires a reason and confirmation. It removes that category's
   selected month/year upload and deactivates its exclusive master entries, removing
   them from the active catalog. Entries shared with another active month stay active.
   Other periods, mapping IDs, historical uploads and audits are retained. Removed
   items cannot be used in new planning until re-uploaded; matching imports
   reactivate the same master IDs.

Save or discard edits before changing periods, uploading, deleting or exporting.
Delete existing period data before uploading a replacement; direct overwrite is
rejected by the API and disabled in the UI. Older unassigned data must also be
reviewed and removed first. Deletion retains snapshots and audits. A version check
rejects stale edits/deletions; edits also reject shared masters changed since the
snapshot. Existing catalog entries are not silently assigned to a month. Clear old
unassigned data, then upload the workbook to establish a dated snapshot.

## Implementation and deployment

- API prefix `/api/v1/masters/product-master/{category}/period`, categories
  `consumables`, `sales_parts`, `assemble`; query `month=1..12`, `year=2000..2100`.
- GET reads, POST uploads, PATCH saves changed fields, DELETE removes the active
  period snapshot, GET `/period/export` exports `.xlsx`.
- GET/DELETE `/api/v1/masters/product-master/{category}/existing-data` reviews and
  removes active entries never recorded in a monthly upload. A content/version
  fingerprint prevents deleting data changed since review. Entries from any dated
  upload, including retained history, are excluded from this cleanup.
- Explicit `masters_read/create/update/delete` flags gate their corresponding
  operations; Super Admin bypass applies. Canonical master updates and audits
  commit in the same transaction as the period snapshot. Rates/counts use Decimal.
- `master_upload_batches` stores snapshots with one active upload per category and
  period, optimistic versions and retained deletion/supersession history.
- Frozen Alembic revision `e002_master_period_uploads` joins the two checked-out
  heads. Existing migration files were not rewritten.
- The configured database has migration ancestry unavailable in this checkout.
  The explicit additive deployment command below creates only the new table/index,
  using the frozen migration, without replaying old migrations or stamping the
  existing revision. It was applied successfully; the table, 12 columns, unique
  active-period index and PostgreSQL RLS were verified. No live master/business
  rows or permissions were edited. Database revision was preserved by the command.

```powershell
cd C:\KN\backend
.\.venv\Scripts\python.exe -m app.db.setup_master_uploads
```

This command is idempotent and explicit; startup/API requests never create tables.
Reconcile missing migration ancestry before future general Alembic upgrades.

## Focused verification

- Ten isolated backend cases cover all categories, month/year isolation, export,
  retained deletion, exact Decimal saves, stale/protected edits, rollback and HTTP
  permissions, unassigned cleanup, delete-before-replace and stable-ID reactivation.
  No company data is used.
- Eleven frontend checks cover existing Product Master forms and the new period
  controls, upload, edit/save, deletion, older-data review, upload blocking and
  export/read-only permissions.
- Additive migration smoke check passes twice on an isolated database, preserving
  an unknown revision. Local Alembic graph has one head.
- TypeScript and production build pass. Running backend exposes the new routes.
- No unrelated full test suites, commit or push were run for this feature.
- The follow-up removal flow needs no further migration. No company master rows
  were deleted/deactivated by the agent; the user reviews and executes deletion
  from the workspace.
