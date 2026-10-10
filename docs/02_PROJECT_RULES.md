# Project Rules

## Business truth
1. Company-approved business rules are authoritative.
2. Existing Excel is evidence of current process, not automatically the correct future rule.
3. Never copy broken Excel formulas blindly.
4. Never invent missing formulas/norms.
5. Every calculation must be explainable from stored inputs and rule parameters.
6. Critical changes require audit history.

## Central inventory
- KNL has one common central consumable store.
- Plant demand is plant-specific.
- Purchase planning uses central inventory.
- Do not create five independent purchase stores unless KNL confirms separate controlled plant stock.

## Requirements
Where an approved formula exists:
`PRD/Production → Approved Rule → Calculated Requirement → Plant Confirmation → Approved Exceptions → Final Requirement`

Do not double-count a normal plant request already represented by production-derived demand.

Additional requirements require:
- quantity
- reason/category
- requesting plant/user
- timestamp
- approval status

## Purchase
Recommendation may consider:
- final requirement
- current usable stock
- confirmed incoming PO/GRN
- MSL
- lead time
- target stock
- MOQ
- pack size
- order multiple
- supplier constraints

The ERP recommends; authorized humans approve.

## Revisions
Planning revisions are records/versions. Never hard-code R1/R2 as permanent columns.

## Precision
Use Python `Decimal` and PostgreSQL `NUMERIC` for money and precise business quantities.

## No hidden logic
Each recommendation must be traceable to source data, rule/version, stock, incoming supply, MSL, lead time, constraints, adjustments and approvals.
