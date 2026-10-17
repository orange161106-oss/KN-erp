# KNL Consumable ERP — Documentation Index

This `docs/` folder is the single source of truth for the KNL Consumable ERP.

If code and documentation disagree, stop and resolve the conflict before continuing.

## Mandatory AI read order
1. `01_PROJECT_SCOPE.md`
2. `02_PROJECT_RULES.md`
3. `03_TECH_STACK.md`
4. `04_SYSTEM_ARCHITECTURE.md`
5. `05_DOMAIN_BUSINESS_RULES.md`
6. `06_DATABASE_AND_API_RULES.md`
7. `07_AI_BUILD_RULES.md`
8. `08_TEAM_OWNERSHIP.md`
9. `09_GIT_WORKFLOW.md`
10. `10_TESTING_SECURITY_DOD.md`
11. `11_ROADMAP.md`
12. `12_AI_TASK_TEMPLATE.md`
13. relevant file in `team/`
14. relevant ADR in `adr/`

## Finalized stack
- React + TypeScript + Vite
- Tailwind CSS
- Python + FastAPI + Pydantic
- PostgreSQL
- SQLAlchemy
- Alembic
- openpyxl
- pandas only where genuinely useful
- Celery + Redis only when background/scheduled jobs become necessary

## Golden rule
AI must never invent a manufacturing/business rule. Unknown rules must be marked `TBD`.

## Saved project context

[Code and workflow context](PROJECT_CONTEXT.md) records the 2026-10-13 review,
current screen/service paths, recent approved UI changes, and unresolved integration
issues. Use it for orientation, then verify current code and the governing contracts.

[Performance and connection validation](validation/PERFORMANCE_RELIABILITY_2026-10-15.md)
records the latest optimization measurements, tests and remaining hosting limits.

[Product Master catalog](validation/PRODUCT_MASTER_CATALOG_2026-10-15.md) records the
current undated upload → review → Save changes flow, count reconciliation, deletion
and focused checks. The earlier monthly upload design is retained as a historical
deployment record only.

## Shared implementation contracts

- [Company monthly purchase formula](25_COMPANY_MONTHLY_PURCHASE.md): owner-supplied
  KNL-Formula.xlsx, selected-month uploaded MSL/MOQ, previous closing stock, monthly
  preview versus saved timed assessments, and explicit missing-input handling.

- [Central basic consumable planning](24_CENTRAL_BASIC_PLANNING_CONTRACT.md):
  owner-approved direct production → norms → central Super Admin review → inventory/
  purchase workflow, reviewed files, source/approval evidence, migration and QA limits.

- [M1.3 authentication and RBAC](13_AUTH_RBAC_CONTRACT.md): schema, login/current-user
  API, centralized permission checks, token configuration and remaining authority TBDs.
- [M2.3 consumable, unit and supplier masters](15_CONSUMABLE_SUPPLIER_MASTER_CONTRACT.md):
  master APIs, inactive behavior, audit records, permissions, UI and supplier-field TBDs.
- [KNL business decision register and questionnaire](16_KN_BUSINESS_DECISION_REGISTER.md):
  Munees's stock-flow confirmations, remaining KNL questions and the milestone in
  which each decision is needed.

- [M4.1 central inventory](17_CENTRAL_INVENTORY_CONTRACT.md): KNL's existing-ERP
  ownership, immutable source import, reported balances/history, exact conversion,
  technical permissions and remaining integration decisions.

- [M4.2 projected inventory](18_PROJECTED_INVENTORY_CONTRACT.md): exact event
  projection, approved MSL evidence, lead-time interval integration, reconciled
  source inputs, consistent reads and explicit timing limitations.

- [M4.3 reorder timing](19_REORDER_TIMING_CONTRACT.md): supplied-policy assessment,
  lead-time deadlines, working-calendar boundaries, explanations and nullable results.

- [M5.1 purchase recommendation](20_PURCHASE_RECOMMENDATION_CONTRACT.md): provisional
  quantity rules, simultaneous supplier constraints, explicit targets and explanations.

- [M5.3 purchase orders](21_PURCHASE_ORDER_CONTRACT.md): traced approved demand,
  transaction-safe PO commitments, pricing, API/UI and fulfilment limitations.

- [M5.4 GRNs and inventory](22_GRN_INVENTORY_CONTRACT.md): atomic posted-ERP receipt
  imports, accepted-only fulfilment, source stock links, permissions and retry rules.
- [M6.2 inventory and purchase reports](23_INVENTORY_PURCHASE_REPORTS_CONTRACT.md):
  authoritative domain report sources, filters, non-live coverage, permissions,
  query performance and remaining definition questions.
