# M7.2 — Inventory/purchase golden validation handoff

Owner: Munees. Reviewer: TBD (not specified for M7.2).
Branch: `feature/munees/m7.2-inventory-purchase-golden-cases`.
Validated: 2026-10-06. **Technical comparisons ready for review; KNL acceptance pending.**

## Result and remaining dependency

Twelve independently worked **synthetic** cases match the authoritative services:
zero differences, zero replay errors. The available company inventory PDF contains
scope decisions and TBD quantities/dates; it supplies no complete numeric purchase
example. Munees does not currently know where approved examples are stored. A source
guide and blank KNL capture sheet are supplied. The company registry is empty,
company acceptance remains pending, and this milestone is not claimed complete.

Company differences are not assessed, rather than reported as zero. KNL must provide
and approve real inputs and independent expected answers. The assigned reviewer
must inspect evidence and close every resulting difference before company sign-off.

## Changes

- Test-only replay uses stock import/balance, M4.2 projection, M4.3 reorder and M5.1
  recommendation services in isolated in-memory databases. Upstream final requirement
  is a supplied approved fixture, not a recalculated requirement rule.
- Case files record stock, incoming schedules, requirement reconciliation/timing,
  MSL/history/policy, supplier, lead time/calendar, target, constraints and independent
  expected quantities/dates. Cases use exact Decimal input contracts.
- Comparison retains all field/timeline differences, missing fields and replay
  errors, with investigation status OPEN. Reports include source/expected evidence,
  actual explanations, case-file fingerprints and executed engine versions.
- A company marker and CLI gate distinguish company acceptance from synthetic
  validation. Empty/invalid company cases return exit 2 instead of a false pass.
- Capture/storage/investigation documentation and business-decision status updated.

No production business formula, API, UI, schema, migration, environment setting or
permission grant changed. No operational database was read or written. Existing
ERP remains the stock/receipt authority. Reviewer must not treat fixture values as
supplier defaults, target policy or KNL numeric approval.

## Actual validation

Existing scope suite:

```text
pytest app/tests/test_inventory.py app/tests/test_projection.py app/tests/test_reorder.py app/tests/test_purchase_recommendation.py app/tests/test_grns.py
202 passed, 5 warnings in 35.93s
```

New final replay/comparison suite:

```text
pytest app/tests/test_inventory_purchase_golden.py
34 passed, 1 skipped, 5 warnings in 2.03s
SKIPPED: M7.2 KNL acceptance PENDING: no complete company-approved numeric cases supplied
```

CLI, final recorded fixtures:

```text
MATCH: 12 cases; company acceptance PENDING
exit 0; difference_count=0; replay_error_count=0

NOT_READY: 0 cases; company acceptance PENDING
exit 2
```

Technical case-file SHA-256 at execution:
`3db1f357cd816b3c48fa7f3a582b269b75f7ed4813d4aa341a22125a8cba979b`.
Executed service versions: `M4.2_V1`, `M4.3_V1`, `M5.1_V1`.
Generated reports: `backend/.cache/m7_2/technical_report.json` and
`backend/.cache/m7_2/company_report.json` (ignored, reproducible local artifacts).

Existing PostgreSQL scope suite:

```text
pytest app/tests/integration/test_inventory.py app/tests/integration/test_projection.py app/tests/integration/test_reorder.py app/tests/integration/test_purchase_recommendation.py app/tests/integration/test_grns.py
28 skipped, 5 warnings in 0.17s
Reason: TEST_DATABASE_URL not configured for a disposable PostgreSQL database ending in _test
```

Thus **236 related checks passed**, one company-case check and 28 PostgreSQL checks
were skipped. The full repository/frontend suite was not run; runtime/UI code was
unchanged. PostgreSQL concurrency/rollback results are not claimed for this run.
The five existing warnings are Starlette/AnyIO and class-based Pydantic config
deprecations. `git diff --check` passed for tracked changes.

## Interpretation and review

All technical differences: none. T04's reorder true / later purchase zero is
intentional: late incoming restores stock at the proposed purchase receipt but
does not prevent the earlier MSL breach. Do not invent earlier supply or a buffer
to make those separate questions produce the same action.

Review [the validation contract](../docs/24_INVENTORY_PURCHASE_GOLDEN_CASES.md),
[case capture sheet](../docs/validation/M7_2_KNL_CASE_CAPTURE.md),
[independent arithmetic](app/tests/data/inventory_purchase/technical_expected_results.md)
and case replay. Obtain KNL source exports, approved requirement timing, policy and
supplier terms; normalize reviewed cases into `company_cases.json`. Inspect the
named approval and source fingerprints, run company comparisons, investigate every
difference and obtain sign-off. Keep previous evidence/results when rules change.

Cross-team boundary: Yathish's final requirement and Keerthi's approval evidence
are consumed through existing contracts. No upstream formula/authority is changed.
Munees coordinates company inputs; KNL decides operational quantities and policies.
The reviewer for this milestone remains TBD. No PR, merge or production acceptance
was performed by this validation work.
