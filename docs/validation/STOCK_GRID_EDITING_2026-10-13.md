# Stock statement and stock management editing

Inventory operators with inventory_update (or Super Admin) can correct statement
quantity/value and description fields, and stock management descriptions, limits,
MOQ and lead time. Item IDs, categories and units remain protected identifiers.

Double-click or F2 edits a cell. The right-click menu supports Edit cell, Edit row,
Copy, Paste and Clear cell for editable fields. Ctrl+C/V uses native clipboard
handling; tab/newline paste fills the visible range starting at the selected cell.
Read-only columns and out-of-bounds ranges reject the paste without partial edits.
Clipboard denial is displayed with a keyboard fallback. Clear means unspecified
(null), not zero. Decimal input is kept as text and validated by backend Pydantic
and Decimal with up to four places; lead time requires whole nonnegative days.

Ctrl+Z undoes unsaved committed edits, including clear, formula bar, row edits and
paste; a rectangular paste is one action. Ctrl+Y or Ctrl+Shift+Z redoes. Inline text
editors keep native text undo until committed. The grid does not intercept unrelated
search/dialog input undo. History is cleared on save/reload, discard and batch change.
Changing filters/periods is disabled while drafts are unsaved: save or discard first.

Ctrl+S commits an active editor before saving. Both correction APIs check backend
inventory_update, period, row ownership and active batch; no edit touches the stock
transaction ledger. Stock statement PATCH /api/v1/inventory/statement/batch-update
requires batch_id, month, year and changed fields in updates. Management uses its
existing batch-update endpoint; it now merges only supplied fields (including explicit
null), rejects invalid rows, and verifies optional batch_id. Current UI sends it.

Updates lock the reviewed batch, record before/after and actor/time in audit history,
and roll back as a whole on failure. Replacement imports lock the same batch.
No database migration or change to historical PO/recommendation evidence is required.
Tests use isolated databases and synthetic UI data; no live uploaded data was edited.


## Cell editor interaction repair

The right-click Edit cell regression reproduced a lost draft: double-clicking the
input bubbled to the table cell and restarted editing with the saved value. Editor
click/double-click/context-menu and Enter/Escape/Tab events now stay in the editor.
Repeated edit requests for the same active cell no longer reset its draft. Focus is
set after React mounts the input, replacing delayed focus callbacks. F2/menu editing
selects the saved text; typing directly into a cell leaves the caret after the first
character so subsequent typing appends normally. Regression tests cover these paths.
Thirty affected frontend tests and the production build passed after this repair.


## Description editing

Item Description in Stock statement and Description in Stock management are now
editable with inventory_update. The screenshot's disabled Edit cell action came
from these columns being marked read-only. Text corrections use the same batch
lock, permission check, before/after audit and rollback paths as numeric changes.
Text is validated separately from numbers, retains punctuation, supports clearing
to null and is limited to 2000 characters. These correct the monthly uploaded
record; they do not rename the consumable master. Integration tests cover right-click
Edit cell, undo, redo and exact text save payload for both pages. The affected checks
passed: 29 backend tests, 27 frontend tests and the production build.
