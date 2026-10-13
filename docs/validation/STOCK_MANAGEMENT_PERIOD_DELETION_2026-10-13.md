# Delete a monthly stock parameter upload

In Inventory → Stock management, select the month/year, choose **Delete parameters**,
enter a reason, and confirm the named period. This deactivates the complete selected
parameter upload, including search-hidden rows. Other months/years, original records,
previous uploads, and audit history remain. Unsaved edits are discarded only after
successful deletion. Existing recommendations and POs are not rewritten.

Access requires the existing inventory_delete flag or Super Admin access. Read,
create/update access and an ADMIN role label alone do not allow deletion.

DELETE /api/v1/inventory/management?month=10&year=2026 accepts a reviewed batch_id
(UUID) and trimmed nonblank reason (maximum 1000 characters). Month is 1–12 and year
is 2000–2100. The batch is locked and its existing status becomes deleted together
with the actor/time and audit record in one transaction. A stale replaced upload
returns 409, a wrong-period upload returns 404, and repeats are idempotent. Audit
or commit failure rolls back the deletion. Inline edits and replacement imports
lock the same batch. No schema migration is needed for the existing string status.

Active parameter reads and purchase lookups already exclude deleted batches. The
UI clears selection, edits, and obsolete requests after deletion and reloads the
selected period. Missing or mismatched periods cannot be deleted.

Validation uses isolated SQLite databases and mocked UI API responses. The new
parameter deletion tests and existing statement deletion tests passed (39 backend
cases). PostgreSQL locking was not exercised against shared Supabase. No live
uploads were deleted. The frontend production build passed; browser verification
used synthetic records with all writes disabled.
