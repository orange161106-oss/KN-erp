# M7.2 — Inventory/purchase golden cases

Owner: Munees. Reviewer: TBD; none named for this milestone.

**Technical validation passed; KNL numeric acceptance pending.** These checks
establish implementation behavior against independently worked technical answers.
They do not approve company targets, supplier terms, MSL policies or calendars.

## Evidence audit — 2026-10-06

The supplied `INV_KN_Discussion_Answers_Updated.pdf` (three pages) confirms scope
decisions INV-01–INV-09. Source SHA-256:
`cab580b5599b0b3fafef9b770c9f95bc11d7845f37f8659693817f3a9d6b0fe7`.
Numeric quantities, units, dates, effective dates and source-record references
remain TBD. INV-08/page 2's stock 1,000 / MSL 500 illustration lacks a material,
dated demand, incoming supply, lead time, target and expected purchase result.
It is neither a complete golden case nor an operational default.

Munees confirmed that the location of approved numeric examples is not currently
known and requested a suggested approach. No complete company-approved numeric
case was found in the repository or supplied inventory PDF. The company registry
is explicitly empty; synthetic cases have not been relabelled as KNL-approved.

## Where to obtain and store cases

| Input | KNL source to request |
|---|---|
| Usable central stock and exact snapshot time | Existing ERP consumable-store stock report, with damaged/rejected/inspection-pending and reserved exclusions |
| Incoming schedules and accepted receipts | Existing ERP PO/delivery schedules, accepted GRNs and cancellations; outstanding usable-availability dates |
| Final requirement and timing | Approved selected planning-version/plant requirement records and explicitly approved dated schedule |
| MSL/history and equality convention | Existing ERP MSL records and KNL-approved effective policy |
| Supplier lead time and calendar | Approved supplier records/quotation; order-initiation to usable-receipt basis and explicit working dates if applicable |
| Target, MOQ, pack, multiple and maxima | Approved target decision and supplier terms; confirm absence explicitly |
| Expected answers | Independently reviewed company calculation/workbook cells with identical units, scope and cutoffs |

Use [the KNL capture sheet](validation/M7_2_KNL_CASE_CAPTURE.md) for each real
material/supplier/version. Keep raw exports and approval evidence in a company-
controlled folder; `backend/.local/m7_2/evidence/` is an ignored local working
location. Record ERP/report parameters or workbook/sheet/cell references and
source SHA-256 fingerprints. Store reviewed normalized cases in
`backend/app/tests/data/inventory_purchase/company_cases.json`. A named KNL
approver, approval time, input/expected references and source fingerprint are
required. Reviewers must inspect the evidence; metadata alone cannot prove approval.

Let KNL select representative materials for no incoming, supply before/after a
breach, exact MSL, already-breached stock, partial receipts/cancellations, and each
applicable constraint. No company quantities are supplied by this milestone.

## Replay and acceptance gate

The test-only runner `app.tests.inventory_purchase_golden` creates a fresh in-memory
SQLite database per case, without reading `.env`, settings or operational databases.
It seeds supplied final demand as an already-approved upstream fixture, then calls
existing stock import/balance, projection, reorder and purchase recommendation
**services**. It does not duplicate business formulas in the validator.

This validates the supplied-final-demand boundary, not upstream requirement formulas,
an ERP connector, live stock, authorization or PostgreSQL locking. Existing API/GRN
and PostgreSQL integration suites cover those boundaries. There are no production
code, API, UI, migration, environment or permission-grant changes.

Cases record material/unit/supplier, stock exports, final/fulfilled/reserved demand
per plant, dated remaining demand, incoming schedules, already accepted/received and
cancelled quantities, effective MSL, policy, lead time/calendar, evaluation/horizon,
initiation/receipt, target and every constraint's applicability. Inputs use existing
Pydantic contracts. Expected quantities are decimal strings, with four-place
precision. Unknown incoming/timing/constraints stay unknown, not zero/defaults.
Normalized incoming `received_quantity` means accepted quantity already accounted
for at the baseline; rejected material cannot fulfil a PO or enter usable stock.
The existing services handle reconciliation, outstanding supply and exclusions.

The report retains inputs, independent expected answers, actual service explanations,
case-file fingerprint, executed engine versions and **every** difference. Missing
fields cannot match an expected null. Equivalent decimal formatting and UTC offsets
do not cause false differences. Replay errors are recorded; other cases continue.
Expected answers are never populated from the engine being tested.

From `C:\KN\backend`:

```powershell
.\.venv\Scripts\python.exe -m pytest app/tests/test_inventory_purchase_golden.py
.\.venv\Scripts\python.exe -m app.tests.inventory_purchase_golden --report .cache/m7_2/company_report.json
.\.venv\Scripts\python.exe -m app.tests.inventory_purchase_golden --cases app/tests/data/inventory_purchase/technical_cases.json --report .cache/m7_2/technical_report.json
```

Exit 0: all supplied cases match. Exit 1: differences/replay errors. Exit 2: empty
or invalid cases. A technical match retains `company_acceptance=PENDING`. An empty
company suite returns `NOT_READY`, exit 2; pytest displays a named skip. Require
the company CLI to exit 0, evidence review and sign-off before closing company UAT.

## Recorded technical cases and findings

T01–T12 are explicitly synthetic. Independently worked quantities and dates are in
[technical_expected_results.md](../backend/app/tests/data/inventory_purchase/technical_expected_results.md);
full inputs and fixed expected answers are in adjacent `technical_cases.json`.
The technical text-source hash uses canonical UTF-8/LF for cross-platform checkouts.

Coverage: snapshot precedence; no incoming; short/long lead time; supply before/after
breach; partial received/cancelled and late supply; exact MSL under both equality
policies; already breached stock; negative projection; four-place Decimal;
simultaneous pack/multiple rounding; MOQ; maximum conflict; unknown constraint;
zero raw demand. Existing suites also check damaged/unposted source rejection,
issue/usable-return direction, conversions, missing timing, receipts, rollback and
permissions. PostgreSQL integration checks require the existing disposable test DB.

All 12 technical cases match: zero numeric differences and zero replay errors.
T04 intentionally requires reorder for an earlier breach while purchasing at the
later receipt gives zero: later recovery does not prevent an earlier MSL crossing.
This follows the separate timing/quantity contracts and is not a discrepancy.
Zero company cases were compared; company differences are **not assessed**.

## Difference investigation and completion

For each mismatch/error, preserve case/field, expected, actual, source evidence,
impact, root cause, owner, correction/approval and retest. Classify the cause as
source data, unit conversion, timing/cutoff, received/reserved double counting,
policy/constraint interpretation, implementation, or incorrect legacy workbook.
Missing policy remains TBD rather than a number to tune. Never force a match to
a known-wrong Excel formula.

Fix implementation defects with regression cases. Correct a source or independent
expectation only with recorded confirmation; obtain KNL approval for policy changes.
The runner marks differences `investigation=OPEN`; evidence/review close them.
Rerun affected cases and retain earlier reports. To finish M7.2, obtain complete
approved cases, inspect their evidence, run comparisons, close every difference,
and obtain assigned-reviewer and KNL sign-off.
