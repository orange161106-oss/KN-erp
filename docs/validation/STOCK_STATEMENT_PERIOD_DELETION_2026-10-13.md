# Delete a selected stock statement period

Owner/module: Munees / central inventory.

In Inventory → Stock statement, select a month and year, choose **Delete statement**,
enter a reason, and confirm the named period. The operation removes the entire
active upload, including rows hidden by search, warnings, or item-class filters.
The button is disabled when that period has no active statement or is still loading.
Users need the existing `inventory_delete` feature flag, or Super Admin access.
Read, upload, update permissions, and an ADMIN role label alone do not authorize deletion.

## API and transaction

`DELETE /api/v1/inventory/statement?month=9&year=2026`

Body: `batch_id` (the reviewed upload UUID) and a nonblank `reason` (up to 1000 characters).
Month must be 1–12; year must be 2000–2100. Extra request fields are rejected.

The service locks the matching batch with PostgreSQL `FOR UPDATE`, checks its period
and active status, changes its existing status to `deleted`, and records the actor,
UTC update time, and audit event in one transaction. Audit or commit failure rolls
everything back. Superseded uploads return 409; an upload outside the requested
period returns 404. Retrying deletion of the same deleted upload returns success
without another audit event and cannot affect a later replacement upload.

Other months and years, historical superseded batches, and all original line records
are preserved. There is no hard deletion and no restoration of an older upload to
active status. Existing statement reads, exports, and purchase-source lookups select
only `status = 'active'`, so the removed upload no longer supplies future calculations.
Previously stored purchase recommendations and POs are not rewritten.

No schema migration is needed: the existing batch status column supports this value.
No live uploaded data was deleted during implementation. Tests use synthetic data
in isolated SQLite databases and mocked frontend API responses. PostgreSQL row
locking has not been exercised against the shared production database.
