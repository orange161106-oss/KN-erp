# Company monthly purchase calculation — 2026-10-17

## Owner decisions and workbook source

The owner supplied KNL-Formula.xlsx and selected **Use uploaded Stock Management
MSL and MOQ** for the selected planning month. The supplied workbook is a formula
catalog: Sheet1 has 150 definitions stored as text, rather than a complete source
operating workbook. The original file was read without editing it.
Source SHA-256: `5aca21ff54f396e5e8fcec1cf446c6feb29499689daea567da0f72b0f0e254a7`.

Applicable definitions: Sheet1 row 9 / Plan!S4 reads prior closing via SUMIF; row 20
/ Plan!AB4 carries prior closing into the next month; row 23 / Plan!AD4 calculates
order quantity; row 24 / Plan!AE4 calculates order value. Row 12 describes several
MSL variants; row 14's typed MOQ is an item example. These are not global defaults.

## KNL_MONTHLY_V1

1. Sum saved production-based requirements by consumable and calculation unit.
2. Read the single active **previous month's** Stock Statement. Sum matching item
   closing quantities once, following SUMIF, after validating every matching row's
   unit and item mapping. January uses December of the preceding year.
3. Read the single active **selected month's** Stock Management upload. Resolve
   the existing per-item parameter rows without silently choosing differing
   departmental/category limits. Use uploaded MSL and MOQ as quantities, including
   explicit zeros. Do not derive or replace them with a 10/26-day assumption.
4. `raw gap = MSL + required quantity − previous closing stock`.
5. `recommended quantity = max(raw gap, MOQ)` if raw gap > 0, otherwise zero.
6. `purchase value = recommended quantity × Product Master rate` when rate exists.
   Keep exact Decimal multiplication; no new currency rounding rule is assumed.

The supplied CO2 example gives `981 + 2550 − 235 = 3296`, with MOQ 675. Quantity is
3296 and value at rate 9 is 29664. MOQ never creates an order when the gap is zero
or negative. Negative published closing stock increases the gap. No additional
pack rounding, max cap, PO deduction or lead-time consumption is applied.

Only existing known unit-label synonyms (e.g. NOS/PCS, KG/KGS) match; blank/numeric
labels and cross-unit conversions are not accepted. Missing item, blank closing,
MSL/MOQ, multiple active batches, ambiguous limits, master/unit mismatch or invalid
precision produces explicit input issues and a null recommendation, never a
guessed zero. A missing rate blocks value only, not quantity. Explicit Product
Master supplier identity is displayed only when its supplier/mapping are active;
the implementation never chooses the first supplier alphabetically.

## UI, Excel and workflow boundary

The production-based Purchase Plan API and Excel export share this read-only
calculation. The grid adds MSL, MOQ, rate, value, stock period and calculation basis.
Excel appends these and calculation details/input issues after the existing 18
columns, preserving prior edit/proposal positions. Incoming is labelled **Not used
by monthly formula**, rather than pretending unknown pending supply is zero.
API details identify source batch/file/hash/line/parameter IDs and actual operands.
Both source tables and masters are loaded in batches, without queries per item.

Valid monthly preview quantities are visible while requirements await review.
They do not approve requirements or create approval/PO rows on read/export.
Approved versions with missing sources show MONTHLY_INPUTS_REQUIRED. Positive
complete previews still require the existing Stock and purchase assessment for
submission; no new direct/untraced purchase-submission path was added. Quantity
proposal editing, master editing, existing permissions and plant restrictions stay
in force. This change supplies monthly planning quantities; it does not replace the
M5.1 dated usable-stock/supplier assessment used by purchase demand submission.

Previously submitted traced assessments retain their saved engine version,
stock, incoming, raw/recommended quantities and supplier. They are never recomputed
under KNL_MONTHLY_V1; their basis is displayed in each row. The legacy manually
imported monthly workspace retains its original calculation/approval behavior.
No schema migration or live company data mutation is required for this change.

## Deliberately excluded catalog entries

Consumption formulas remain the configured norms, including the owner's earlier
confirmation that 100 parts × 2 processes = 200 final consumables for that norm.
The formula catalog's tool-life examples do not override this decision. Revised
R2 formulas referencing incorrect/empty stock columns, unrelated paint/packing/
housekeeping formulas and alternate MSL variants were not installed by inference.

## Verification

Focused checks cover the supplied numeric example, MOQ/zero/negative balances,
decimal precision, source month/year isolation, shared stock once, missing and
ambiguous inputs, unit validation, source identity, immutable saved assessments,
read/export side effects, exact Excel values and existing editing/authentication.
Connected-data verification is performed in a READ ONLY / REPEATABLE READ database
transaction; counts and remaining source issues are recorded in PROJECT_CONTEXT.
