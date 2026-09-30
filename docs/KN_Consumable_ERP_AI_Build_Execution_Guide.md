# KN Consumable ERP — AI Build Execution Guide & Prompt Library

This guide is for the 3-member KN Consumable ERP team using Codex, Claude Code, Cursor, Antigravity, or another AI coding agent.

The docs folder is the source of truth. AI-generated code is never allowed to invent company business rules.

---

# 0. Team Ownership

## Munees — Inventory & Purchase Planning
Owns backend/database foundation coordination, consumable/unit/supplier master coordination, central inventory, stock transactions, MSL, supplier lead time, projected inventory, reorder logic, MOQ/pack size/order multiple, purchase recommendation, PO, GRN, pending PO, Inventory Planning Engine and Purchase Planning Engine.

## Keerthi — Plant Workflow, Access, Approvals & Alerts
Owns React application shell coordination, plant/process/route workflow, plant requirement confirmation, additional/exception request workflow, approvals, plant-scoped access, alerts, and workflow/dashboard visibility.

## Yathish — Production & Requirement Calculation
Owns customer/product, PRD import domain, product→plant, product/process→consumable mappings, consumption/business-rule master, planning versions, Requirement Calculation Engine and requirement explanation.

---

# 1. Mandatory AI Session Workflow

Every AI task must follow this sequence.

## A. Read before coding
Read:
- `docs/01_PROJECT_SCOPE.md`
- `docs/02_PROJECT_RULES.md`
- `docs/03_TECH_STACK.md`
- `docs/04_SYSTEM_ARCHITECTURE.md`
- `docs/05_DOMAIN_BUSINESS_RULES.md`
- `docs/06_DATABASE_AND_API_RULES.md`
- `docs/07_AI_BUILD_RULES.md`
- `docs/08_TEAM_OWNERSHIP.md`
- `docs/09_GIT_WORKFLOW.md`
- `docs/10_TESTING_SECURITY_DOD.md`
- relevant `docs/team/<owner>.md`
- relevant ADRs

## B. Plan and stop
Before editing files, return:
1. understanding;
2. dependencies;
3. files expected to change;
4. DB impact;
5. API impact;
6. permission/security impact;
7. business-rule impact;
8. tests;
9. assumptions;
10. unresolved `TBD` items;
11. cross-team impact.

Then STOP. Do not edit until the human replies exactly `APPROVED`.

## C. Implement only approved scope
After approval:
- work only in the named feature branch;
- do not touch unrelated domains;
- preserve React → API → Service → Domain → Repository → PostgreSQL boundaries;
- never put authoritative business formulas in React or FastAPI route handlers.

## D. Verify
Run relevant backend tests, frontend typecheck/build, migration checks, API tests and domain calculation tests. Do not claim success without real verification where the environment permits it.

## E. Completion report
Return:
- files changed;
- migrations created;
- endpoints added/changed;
- tests added/run and real results;
- assumptions/TBD;
- cross-team impact;
- manual checks required;
- risks.

Stop at review-ready branch/PR. Do not merge to `main`.

---

# 2. Branching

Long-lived branches:
- `main`
- `develop`

Feature branch:
`feature/<owner>/<milestone>-<short-name>`

Examples:
- `feature/munees/m1.1-backend-foundation`
- `feature/keerthi/m1.2-frontend-foundation`
- `feature/yathish/m2.1-prd-import`

---

# 3. Build Order

```text
PHASE 0  Human setup + docs + open decisions
   ↓
PHASE 1  Technical foundation
   ↓
PHASE 2  Master data + PRD
   ↓
PHASE 3  Requirement calculation + plant workflow
   ↓
PHASE 4  Central inventory + inventory planning
   ↓
PHASE 5  Purchase planning + PO + GRN
   ↓
PHASE 6  Alerts + reports + history
   ↓
PHASE 7  Excel comparison + pilot validation
   ↓
PHASE 8  Production hardening + deployment
```

Do not run an entire phase as one AI prompt. One prompt = one milestone.

---

# PHASE 0 — HUMAN SETUP

## P0.1 Repository
All three humans:
1. Create one GitHub repository.
2. Add `frontend/`, `backend/`, `docs/`.
3. Put all approved docs in `docs/`.
4. Create `develop`.
5. Protect `main`, and preferably `develop`.
6. Require PR review before merge.
7. Add `.env.example`; never commit real secrets.

## P0.2 Business decisions that AI must NOT invent
Keep unresolved values as `TBD`:
- exact role/permission matrix;
- plant floor-stock behavior;
- actual consumption transaction convention;
- MSQ meaning;
- approver hierarchy/value limits;
- supplier pack/order-multiple rules;
- unresolved consumable formulas;
- requirement timing granularity if not confirmed.

---

# PHASE 1 — TECHNICAL FOUNDATION

## M1.1 — Munees — Backend/Database Foundation
Owner: Munees
Reviewer: Yathish
Depends on: P0
Branch: `feature/munees/m1.1-backend-foundation`

### Prompt
```text
You are the AI development agent for the KN Consumable ERP.

OWNER: Munees
REVIEWER: Yathish
MILESTONE: M1.1 — Backend and database foundation
BRANCH: feature/munees/m1.1-backend-foundation

READ FIRST:
docs/01_PROJECT_SCOPE.md
docs/02_PROJECT_RULES.md
docs/03_TECH_STACK.md
docs/04_SYSTEM_ARCHITECTURE.md
docs/06_DATABASE_AND_API_RULES.md
docs/07_AI_BUILD_RULES.md
docs/09_GIT_WORKFLOW.md
docs/10_TESTING_SECURITY_DOD.md
docs/team/MUNEES.md
docs/adr/ADR-001-tech-stack.md

OBJECTIVE:
Create the shared backend foundation using Python + FastAPI + Pydantic + PostgreSQL + SQLAlchemy + Alembic.

SCOPE:
- Create backend package structure matching architecture docs.
- Environment-based settings.
- SQLAlchemy engine/session handling.
- PostgreSQL connectivity.
- Alembic configuration.
- `/api/v1/health`.
- Consistent base error handling where appropriate.
- Basic backend test configuration.
- `.env.example` names only.
- Backend setup documentation.

DO NOT:
- implement inventory/purchase;
- create business tables unnecessarily;
- add Celery/Redis;
- add business formulas;
- put business logic in routes;
- commit secrets.

EXPECTED OUTPUT:
FastAPI starts, PostgreSQL connection works, Alembic works, health endpoint returns success, tests run.

FIRST RESPONSE MUST BE PLAN ONLY:
Return dependencies, proposed folder structure, settings approach, DB session approach, migration approach, tests, files, risks/TBD. STOP and wait for APPROVED.

AFTER APPROVED:
Implement, run tests and migration validation, report real output, stop review-ready. Do not merge.
```

### Gate
Backend-heavy milestones wait until M1.1 is merged.

---

## M1.2 — Keerthi — Frontend Foundation
Owner: Keerthi
Reviewer: Munees
Depends on: repo exists; merge after M1.1 API convention is known
Branch: `feature/keerthi/m1.2-frontend-foundation`

### Prompt
```text
OWNER: Keerthi
REVIEWER: Munees
MILESTONE: M1.2 — React frontend foundation
BRANCH: feature/keerthi/m1.2-frontend-foundation

Read all mandatory project docs plus docs/team/KEERTHI.md.

OBJECTIVE:
Create React + TypeScript + Vite + Tailwind ERP frontend foundation.

SCOPE:
- frontend structure from docs;
- Tailwind setup;
- app shell: sidebar, header, content, routing;
- typed API client/service foundation;
- API base URL from environment;
- System Status page consuming `/api/v1/health`;
- loading/success/error states;
- placeholder route groups only: Masters, PRD/Planning, Requirements, Inventory, Purchase, Alerts, Reports, Administration.

DO NOT:
- implement business calculations in React;
- invent endpoints;
- create fake permanent business architecture;
- implement final permission matrix.

EXPECTED OUTPUT:
React starts and can show FastAPI/server status.

FIRST RESPONSE:
Plan only: component structure, routing, API client, environment approach, files and verification. STOP for APPROVED.

AFTER APPROVED:
Implement and run typecheck/build/tests. Report real results.
```

---

## M1.3 — Munees — Auth + RBAC Backend Foundation
Owner: Munees
Reviewer: Keerthi
Depends on: M1.1
Branch: `feature/munees/m1.3-auth-rbac-backend`

### Prompt
```text
OWNER: Munees
REVIEWER: Keerthi
MILESTONE: M1.3 — Authentication and RBAC backend foundation

OBJECTIVE:
Implement backend foundation for users, roles and permissions without inventing KN-specific authority rules that remain TBD.

SCOPE:
- users/roles/permissions model;
- password hashing;
- login/current-user endpoint;
- reusable backend permission dependency/check;
- Alembic migration;
- Pydantic schemas;
- tests for allow/deny behavior.

KNOWN ROLE CATEGORIES:
ADMIN, PLANNER, PLANT_INCHARGE, STORE, PURCHASE, APPROVER, MANAGEMENT.
Detailed permissions remain configuration/TBD unless already locked in docs.

DO NOT:
- trust frontend authorization;
- invent approval limits;
- hard-code authorization across route handlers;
- expose password hashes.

FIRST RESPONSE:
Schema/API/security/test plan only. STOP for APPROVED.

AFTER APPROVED:
Implement and run auth/permission tests. Report migration/API impact and actual results.
```

---

## M1.4 — Keerthi — Login + Role-Aware UI Shell
Owner: Keerthi
Reviewer: Munees
Depends on: M1.2 + M1.3
Branch: `feature/keerthi/m1.4-login-role-shell`

### Prompt
```text
OWNER: Keerthi
REVIEWER: Munees
MILESTONE: M1.4 — Login and permission-aware app shell

OBJECTIVE:
Connect React to approved authentication API and create permission-aware navigation.

SCOPE:
- login;
- authenticated app state;
- current-user loading;
- logout;
- protected routes;
- permission-aware sidebar/navigation;
- forbidden screen;
- loading/error handling.

SECURITY:
Backend remains authoritative. Hiding a UI element is not security.

DO NOT:
- invent permissions not supplied by backend;
- scatter role checks everywhere; centralize them;
- implement business modules yet.

FIRST RESPONSE:
Plan only. STOP for APPROVED.

AFTER APPROVED:
Verify valid login, invalid login, protected route, forbidden behavior and logout; run typecheck/build/tests.
```

---

## M1.5 — Yathish — PRD & Requirement Contract Design
Owner: Yathish
Reviewer: Munees
Depends on: M1.1
Branch: `feature/yathish/m1.5-prd-requirement-contract`

### Prompt
```text
OWNER: Yathish
REVIEWER: Munees
MILESTONE: M1.5 — PRD and Requirement domain contract

OBJECTIVE:
Before building import/calculation code, define canonical PRD input and calculated-requirement contracts.

SCOPE:
- canonical PRD schema proposal;
- planning_version concept;
- calculated requirement output contract;
- required IDs: product, plant, process, consumable, business rule, planning version;
- calculation explanation structure;
- statuses needed for handoff to plant workflow.

DO NOT:
- invent missing workbook/company fields;
- implement unapproved formulas;
- add inventory/purchase concepts;
- make permanent DB schema before review.

EXPECTED OUTPUT:
Design/doc proposal and explicit TBD list.

FIRST RESPONSE:
Proposal only. No production code. STOP for APPROVED.
```

---

# PHASE 1 GATE
Before Phase 2:
- React ↔ FastAPI ↔ PostgreSQL works;
- Alembic works;
- auth/RBAC foundation works;
- shared error/API conventions exist;
- PRD/requirement contract reviewed.

---

# PHASE 2 — MASTER DATA + PRD

## M2.1 — Yathish — Product/Customer + PRD Import/Staging
Owner: Yathish
Reviewer: Keerthi
Branch: `feature/yathish/m2.1-prd-import`

### Prompt
```text
OWNER: Yathish
REVIEWER: Keerthi
MILESTONE: M2.1 — Product/Customer and PRD import staging

OBJECTIVE:
Build a safe PRD import pipeline. Excel data must not directly become approved planning data.

SCOPE:
- product master;
- customer master if required by approved PRD contract;
- planning_versions;
- import_batches/import_errors;
- PRD order/header/items;
- `.xlsx` upload with openpyxl;
- staging and validation;
- upload/status/error APIs;
- minimal React import/review UI if within this milestone's approved files.

VALIDATE:
headers, required values, numeric quantities, duplicates, unknown products/mappings, file type/size.

DO NOT:
- calculate consumables yet;
- silently auto-create unknown products;
- bypass staging;
- invent spreadsheet columns.

TESTS:
valid file, missing header, invalid qty, duplicate, unknown product, empty file, wrong type.

FIRST RESPONSE:
Plan/schema/API/import-validation/test plan only. STOP for APPROVED.
```

---

## M2.2 — Keerthi — Plant + Process + Route Masters
Owner: Keerthi
Reviewer: Yathish
Branch: `feature/keerthi/m2.2-plant-process-route`

### Prompt
```text
OWNER: Keerthi
REVIEWER: Yathish
MILESTONE: M2.2 — Plant, process and route masters

OBJECTIVE:
Create controlled masters for plants, processes and ordered production routes.

SCOPE:
- plant master;
- process master;
- production routes;
- route steps with sequence;
- backend CRUD APIs;
- React CRUD UI;
- permissions;
- inactive status instead of destructive deletion where history depends on master.

RULE:
One central purchasing store remains the inventory model.

DO NOT:
- implement plant floor stock;
- implement inter-plant transfer;
- invent actual product routes;
- duplicate product mapping owned by Yathish.

TESTS:
CRUD, uniqueness, route sequence, inactivation, unauthorized mutation.

FIRST RESPONSE:
Plan/schema/API/UI/security/test plan. STOP for APPROVED.
```

---

## M2.3 — Munees — Consumable + Unit + Supplier Masters
Owner: Munees
Reviewer: Keerthi
Branch: `feature/munees/m2.3-consumable-supplier-masters`

### Prompt
```text
OWNER: Munees
REVIEWER: Keerthi
MILESTONE: M2.3 — Consumable, unit and supplier masters

OBJECTIVE:
Create purchasing/inventory master-data foundations without purchase calculations.

SCOPE:
- units;
- consumables;
- suppliers;
- supplier_consumables;
- approved supplier-specific fields only;
- APIs and React CRUD;
- inactive status rather than unsafe deletion.

Potential fields such as lead_time_days, MOQ, pack_size, order_multiple may be added only if semantics are approved. Unknown meanings are TBD.

DO NOT:
- invent MSQ meaning;
- invent default supplier values;
- implement purchase recommendation;
- duplicate requirement-rule storage.

TESTS:
unique codes, unit validation, supplier mapping, Decimal validation, permissions, inactive behavior.

FIRST RESPONSE:
Plan/schema/API/UI/TBD list. STOP for APPROVED.
```

---

## M2.4 — Yathish — Product→Plant→Process→Consumable Mapping
Owner: Yathish
Reviewer: Keerthi
Depends on: M2.1 + M2.2 + M2.3
Branch: `feature/yathish/m2.4-production-consumable-mapping`

### Prompt
```text
OWNER: Yathish
REVIEWER: Keerthi
MILESTONE: M2.4 — Production-to-consumable mapping

OBJECTIVE:
Create mapping chain used by Requirement Engine: Product -> Plant -> Route/Process -> Consumable.

SCOPE:
- product_plant mapping;
- product/process-consumable mapping;
- active/effective state;
- validation;
- APIs/UI to maintain mappings.

DO NOT:
- calculate quantities yet;
- invent mappings;
- duplicate route models;
- encode plant requests as mapping rules.

EXPECTED OUTPUT:
For an approved product, system can resolve plant(s), ordered process route and mapped consumables.

FIRST RESPONSE:
Plan/schema/relationship design only. STOP for APPROVED.
```

---

# PHASE 2 GATE
One configured product must resolve:
`PRD Product → Plant → Route → Process → Consumable`.

---

# PHASE 3 — REQUIREMENT CALCULATION + PLANT WORKFLOW

## M3.1 — Yathish — Business Rule/Norm Framework
Owner: Yathish
Reviewer: Munees
Branch: `feature/yathish/m3.1-rule-framework`

### Prompt
```text
OWNER: Yathish
REVIEWER: Munees
MILESTONE: M3.1 — Consumption rule/norm framework

OBJECTIVE:
Build configurable deterministic Requirement Calculation rule framework.

SUPPORTED RULE TYPES:
PRODUCTION_RATE
AREA_COVERAGE
PACKING_RATIO
TOOL_LIFE
FIXED_QUANTITY
PLANT_REQUEST
MAINTENANCE
MIN_MAX

SCOPE:
- business_rule/consumption_norm model;
- version/effective dates/status;
- typed parameters;
- unit;
- rounding policy representation;
- validation required parameters per implemented type;
- pure domain handler/strategy design selected by rule_type.

DO NOT:
- write `if consumable == "CO2"`;
- couple pure calculation handlers to SQLAlchemy;
- invent parameters/formulas.

TESTS:
parameter validation, invalid denominator, inactive rule, missing rule, Decimal.

FIRST RESPONSE:
Architecture/schema/rule-handler/test plan only. STOP for APPROVED.
```

---

## M3.2 — Yathish — First Golden Rule
Owner: Yathish
Reviewer: Munees
Depends on: M3.1
Branch: `feature/yathish/m3.2-first-golden-rule`

### Prompt
```text
OWNER: Yathish
REVIEWER: Munees
MILESTONE: M3.2 — First approved deterministic calculation

OBJECTIVE:
Implement ONE approved rule end-to-end before expanding rule types.

PREFERRED:
Use an approved formula-driven example such as packing box or powder coating. Do not start with CO2 unless KN confirms its future formula.

OUTPUT MUST EXPLAIN:
planning version, production source, product, plant, process, consumable, rule type/version, parameters, calculation steps, raw result, rounding, final qty, unit.

DO NOT:
- implement all rule types;
- force ERP to match known-wrong Excel output;
- hide rounding.

TESTS:
golden case, zero qty, invalid denominator, missing mapping, missing rule, rounding.

FIRST RESPONSE:
Show exact proposed rule and expected fixture. If any required parameter is unconfirmed, mark TBD and STOP. Otherwise wait for APPROVED before editing.
```

---

## M3.3 — Yathish — Requirement Calculation Orchestrator
Owner: Yathish
Reviewer: Keerthi
Depends on: M3.2
Branch: `feature/yathish/m3.3-requirement-orchestrator`

### Prompt
```text
OWNER: Yathish
REVIEWER: Keerthi
MILESTONE: M3.3 — Requirement Calculation Engine orchestration

OBJECTIVE:
For an approved planning version, resolve mappings, select approved rules, calculate requirements and persist explainable results.

SCOPE:
- calculated_requirements;
- orchestration service;
- calculation endpoint;
- recalculation/idempotency behavior;
- explicit missing mapping/rule errors;
- explanation payload.

DO NOT:
- implement plant confirmation;
- calculate stock/purchase;
- silently skip errors.

TESTS:
mixed valid/error batch, recalculation, planning revision isolation, Decimal aggregation.

FIRST RESPONSE:
Plan/schema/API/idempotency/test strategy. STOP for APPROVED.
```

---

## M3.4 — Keerthi — Plant Confirmation + Exception Workflow
Owner: Keerthi
Reviewer: Yathish
Depends on: M3.3
Branch: `feature/keerthi/m3.4-plant-confirmation`

### Prompt
```text
OWNER: Keerthi
REVIEWER: Yathish
MILESTONE: M3.4 — Plant confirmation and additional requirement workflow

OBJECTIVE:
Authorized plant users review ERP-calculated requirements and confirm them or submit separately traceable exceptions/additions with reason.

SCOPE:
- confirmation state;
- additional requirement records;
- category/reason;
- requester/time/plant;
- approval status;
- plant authorization;
- React screens;
- audit.

RULE:
Do not replace calculated quantity with a free-form plant number. Do not double-count normal production demand.

DO NOT:
- invent approver hierarchy;
- allow editing `calculated_qty`;
- calculate purchase.

TESTS:
authorized confirm, wrong plant denied, no-reason exception denied, calculated qty immutable, audit.

FIRST RESPONSE:
Workflow/state/schema/API/UI/security/test plan; list approval TBDs. STOP for APPROVED.
```

---

## M3.5 — Keerthi — Requirement Approval + Final Requirement Contract
Owner: Keerthi
Reviewer: Munees
Depends on: M3.4
Branch: `feature/keerthi/m3.5-requirement-approval`

### Prompt
```text
OWNER: Keerthi
REVIEWER: Munees
MILESTONE: M3.5 — Requirement approval and final-requirement handoff

OBJECTIVE:
Approve/reject pending exception requirements and expose one authoritative final requirement to inventory planning.

CONCEPT:
Final Requirement = Calculated Production Requirement + approved additional/special/maintenance/trial/rework/other demand.
Only approved additions contribute.

SCOPE:
- approval/rejection;
- approver/time/comment;
- immutable original values;
- final-requirement read contract;
- audit;
- approval queue UI.

DO NOT:
- invent who may approve if permission is TBD;
- permit self-approval unless explicitly approved;
- overwrite original request/calculated values.

TESTS:
approve/reject, unauthorized approve, rejected excluded, final qty, audit.

FIRST RESPONSE:
State-transition and final-requirement contract plan. STOP for APPROVED.
```

---

# PHASE 3 GATE
Demonstrate:
`Excel PRD → Validated Planning Version → Mapping → Rule → Calculated Requirement → Plant Confirmation → Approved Final Requirement`.

---

# PHASE 4 — CENTRAL INVENTORY + INVENTORY PLANNING

## M4.1 — Munees — Central Inventory Ledger
Owner: Munees
Reviewer: Keerthi
Branch: `feature/munees/m4.1-central-inventory`

### Prompt
```text
OWNER: Munees
REVIEWER: Keerthi
MILESTONE: M4.1 — Central inventory and stock transactions

OBJECTIVE:
Implement one central consumable-store inventory ledger.

SCOPE:
- stock transactions;
- approved movement types: opening, receipt/GRN, issue, return, adjustment as confirmed;
- source reference;
- consumable/unit;
- Decimal quantity;
- event time/actor;
- adjustment reason;
- current usable balance service;
- stock history API/UI.

RULE:
Do not model five independent purchasing stores.

DO NOT:
- invent plant floor stock;
- directly overwrite balances without auditable transactions;
- call purchase quantity consumption.

CONCURRENCY:
Stock-changing operations must be transaction-safe.

FIRST RESPONSE:
Ledger/balance strategy, exact transaction semantics, concurrency and tests. If issue/return convention is TBD, state it and STOP.
```

---

## M4.2 — Munees — MSL + Projected Inventory Engine
Owner: Munees
Reviewer: Yathish
Depends on: M4.1 + M3.5
Branch: `feature/munees/m4.2-projected-inventory`

### Prompt
```text
OWNER: Munees
REVIEWER: Yathish
MILESTONE: M4.2 — MSL and projected inventory

OBJECTIVE:
Calculate time-aware projected stock using final requirements, current stock and confirmed incoming supply.

CONCEPT:
Projected Stock(t) = Current Usable Stock + Confirmed Receipts Before t - Forecast Requirement Before t.

SCOPE:
- MSL config/history if approved;
- lead-time input integration;
- projected inventory domain engine;
- explanation;
- below-MSL and future-breach conditions.

DO NOT:
- treat MSL alone as complete reorder logic;
- subtract pending PO twice;
- invent daily/weekly spreading of monthly requirement;
- invent safety buffer.

IMPORTANT:
If requirement timing granularity is not confirmed, surface the limitation instead of guessing.

TESTS:
no incoming, incoming before/after breach, exactly MSL, future breach, double-count protection.

FIRST RESPONSE:
Timeline model, formulas, assumptions/TBD and tests. STOP for APPROVED.
```

---

## M4.3 — Munees — Reorder Timing
Owner: Munees
Reviewer: Keerthi
Depends on: M4.2
Branch: `feature/munees/m4.3-reorder-timing`

### Prompt
```text
OWNER: Munees
REVIEWER: Keerthi
MILESTONE: M4.3 — Reorder timing

OBJECTIVE:
Determine whether/when an order must be initiated so supplier lead time does not allow projected stock to violate the approved MSL policy.

INPUTS:
projected stock, MSL, lead time, confirmed incoming, requirement timeline.

OUTPUT:
reorder_required, expected MSL crossing bucket/date, latest safe order point where determinable, explanation.

DO NOT:
- invent uncertainty buffer;
- reproduce old Excel lead-time behavior blindly;
- calculate purchase quantity yet.

TESTS:
lead time shorter/longer than stock cover, no breach, already breached, incoming prevents breach.

FIRST RESPONSE:
Formula/timeline assumptions/tests only. STOP for APPROVED.
```

---

## M4.4 — Keerthi — Inventory Alerts
Owner: Keerthi
Reviewer: Munees
Depends on: M4.2/M4.3
Branch: `feature/keerthi/m4.4-stock-alerts`

### Prompt
```text
OWNER: Keerthi
REVIEWER: Munees
MILESTONE: M4.4 — MSL/shortage/reorder alert workflow

OBJECTIVE:
Present backend-generated inventory planning events: below MSL, projected MSL breach and reorder required.

SCOPE:
- alert lifecycle/read model if approved;
- severity/status;
- consumable/reference;
- explanation link;
- acknowledgement if required;
- React alert center/dashboard cards;
- deduplication strategy.

DO NOT:
- recalculate projected inventory in React;
- invent thresholds;
- create duplicate alert spam.

FIRST RESPONSE:
Alert lifecycle/dedup/API/UI/test plan only. STOP for APPROVED.
```

---

# PHASE 5 — PURCHASE PLANNING + PO + GRN

## M5.1 — Munees — Purchase Recommendation Engine
Owner: Munees
Reviewer: Yathish
Depends on: M4.3
Branch: `feature/munees/m5.1-purchase-recommendation`

### Prompt
```text
OWNER: Munees
REVIEWER: Yathish
MILESTONE: M5.1 — Purchase recommendation

OBJECTIVE:
Calculate explainable recommended purchase quantity from approved demand, projected availability and supplier constraints.

CONCEPT:
Raw Purchase Qty = Target Stock at Receipt - Projected Available Stock at Receipt.
Then apply approved MOQ, pack size, order multiple, supplier constraints, target/max constraints where confirmed.

OUTPUT MUST SHOW:
final requirement, current/projected stock, incoming, MSL, lead time, target if used, raw qty, MOQ, pack size, order multiple, supplier and recommended qty.

DO NOT:
- auto-create PO;
- invent target stock;
- invent supplier constraints;
- use binary float.

TESTS:
raw<=0, below MOQ, multiple rounding, pack rounding, incoming, missing constraint, Decimal.

FIRST RESPONSE:
Formula precedence/constraint order proposal. If MOQ-vs-pack-vs-multiple precedence is not approved, mark TBD and STOP.
```

---

## M5.2 — Keerthi — Purchase Approval
Owner: Keerthi
Reviewer: Munees
Depends on: M5.1
Branch: `feature/keerthi/m5.2-purchase-approval`

### Prompt
```text
OWNER: Keerthi
REVIEWER: Munees
MILESTONE: M5.2 — Purchase approval

OBJECTIVE:
Allow authorized humans to approve/reject/override a system recommendation.

SCOPE:
- recommendation status transitions;
- approved qty;
- override reason;
- approver/time;
- audit;
- approval queue UI;
- backend permissions.

RULE:
Keep recommended and approved quantities separately. Never silently replace recommendation.

DO NOT:
- invent value-based approval authority;
- auto-approve;
- use UI-only security.

TESTS:
approve exact, override with reason, missing reason denied where required, unauthorized denied, audit.

FIRST RESPONSE:
State/permission/TBD/test plan. STOP for APPROVED.
```

---

## M5.3 — Munees — Purchase Orders
Owner: Munees
Reviewer: Keerthi
Depends on: M5.2
Branch: `feature/munees/m5.3-purchase-orders`

### Prompt
```text
OWNER: Munees
REVIEWER: Keerthi
MILESTONE: M5.3 — Purchase Orders

OBJECTIVE:
Create PO from approved purchase demand while preserving complete traceability.

SCOPE:
- purchase_orders/items;
- supplier;
- approved recommendation reference;
- ordered qty/rate/value where approved;
- PO date;
- expected delivery;
- status;
- pending qty;
- API/UI.

RULE:
PO is a commitment, not stock receipt and not consumption.

TESTS:
create from approved recommendation, deny rejected/unapproved, pending qty, Decimal value.

FIRST RESPONSE:
Schema/state/API/traceability/test plan. STOP for APPROVED.
```

---

## M5.4 — Munees — GRN + Pending PO + Inventory Integration
Owner: Munees
Reviewer: Keerthi
Depends on: M5.3 + M4.1
Branch: `feature/munees/m5.4-grn-integration`

### Prompt
```text
OWNER: Munees
REVIEWER: Keerthi
MILESTONE: M5.4 — GRN and inventory integration

OBJECTIVE:
Post received material against a PO and update central inventory atomically.

SCOPE:
- grns/grn_items;
- PO item validation;
- partial receipts;
- received/pending qty;
- PO status;
- stock receipt transaction;
- audit/source reference;
- API/UI.

ATOMICITY:
GRN + PO received/pending update + inventory receipt must all succeed or all roll back.

DO NOT:
- directly edit stock balance;
- treat ordered qty as received stock;
- invent over-receipt policy.

TESTS:
full, partial, duplicate protection, invalid PO item, concurrent receipt, rollback on failure.

FIRST RESPONSE:
Transaction/locking/idempotency/schema/test plan. STOP for APPROVED.
```

---

## M5.5 — Keerthi — PO Due/Delay Alerts
Owner: Keerthi
Reviewer: Munees
Depends on: M5.3/M5.4
Branch: `feature/keerthi/m5.5-po-delay-alerts`

### Prompt
```text
OWNER: Keerthi
REVIEWER: Munees
MILESTONE: M5.5 — PO due and delay alerts

OBJECTIVE:
Surface delivery risk from authoritative PO/GRN data.

SCOPE:
- overdue;
- partially received overdue;
- due-soon only if threshold approved;
- alert dedup/status/UI.

ARCHITECTURE:
Do not add Celery/Redis automatically. First determine whether on-demand calculation is enough. Scheduled jobs must be a separate approved decision.

FIRST RESPONSE:
On-demand vs scheduled design, conditions, TBDs and tests. STOP for APPROVED.
```

---

# PHASE 6 — HISTORY, REPORTS, DASHBOARD

## M6.1 — Yathish — Planned vs Actual History
```text
OWNER: Yathish
REVIEWER: Munees
MILESTONE: M6.1 — Planned vs actual consumption history

OBJECTIVE:
Expose historical comparison without creating an AI/ML accuracy engine.

SCOPE:
planning version, calculated requirement, approved additions, final requirement, actual stock-based consumption where transaction convention is confirmed, variance amount/%, filters by month/plant/material/process.

DO NOT:
- auto-change norms;
- call purchase consumption;
- infer actual consumption when required stock movements are unavailable.

FIRST RESPONSE:
Data lineage/formula/TBD/test plan. STOP for APPROVED.
```

## M6.2 — Munees — Inventory/Purchase Reports
```text
OWNER: Munees
REVIEWER: Keerthi
MILESTONE: M6.2 — Inventory and purchase reports

REPORTS:
material stock, MSL/reorder, projected shortage, supplier-wise purchase plan, pending PO, GRN, recommendation vs approved vs ordered vs received.

RULE:
Reports consume authoritative domain results; do not recalculate core business logic in report SQL/React.

FIRST RESPONSE:
Report definitions, source of truth, filters, index/performance needs. STOP for APPROVED.
```

## M6.3 — Keerthi — Management Dashboard
```text
OWNER: Keerthi
REVIEWER: Yathish
MILESTONE: M6.3 — Management dashboard

OBJECTIVE:
Build dashboard from existing backend report/alert APIs.

Only show KPIs with real source data: below MSL, reorder required, pending approvals, delayed PO, stock mismatch, requirement/recommended/approved/ordered/received values.

DO NOT recalculate authoritative values in React or invent KPIs.

FIRST RESPONSE:
Exact source endpoint/data contract for every proposed card/chart. STOP for APPROVED.
```

---

# PHASE 7 — EXCEL COMPARISON + PILOT VALIDATION

## M7.1 — Yathish — Requirement Golden Cases
Create approved test cases for representative rule types: packing, area/coverage, tool-life, plant-request, plus others only after formula approval. Record source input, current Excel result, approved future rule, expected ERP result, difference explanation, unit and rounding. Never change engine only to force a known-wrong Excel match.

## M7.2 — Munees — Inventory/Purchase Golden Cases
Validate central stock, MSL, lead-time, reorder and purchase recommendation using approved company examples. Record stock, incoming PO, requirement, MSL, lead time, target, MOQ/pack/multiple and expected result. Investigate every difference.

## M7.3 — Keerthi — Workflow/UAT
Test end-to-end roles: requirement view, confirmation, exception, approval/rejection, inventory, purchase recommendation, purchase approval, PO, partial/full GRN, alerts, audit and unauthorized attempts.

---

# PHASE 8 — PRODUCTION HARDENING

## M8.1 Security & Permission Review
Lead: Keerthi
- permission matrix;
- plant scope;
- ID manipulation tests;
- auth/session behavior;
- secrets;
- upload security;
- audit coverage.

## M8.2 Database & Concurrency Review
Lead: Munees
- stock locking;
- GRN concurrency;
- approval double-submit;
- idempotency;
- indexes/constraints;
- backup/restore;
- migration promotion.

## M8.3 Calculation Regression Suite
Lead: Yathish
- all approved rule types;
- golden cases;
- rounding/Decimal;
- revision isolation;
- missing mappings/rules;
- explanation output.

## M8.4 Celery/Redis Decision
Only add if a real scheduled/heavy workload exists. AI must first show current limitation, expected load/frequency, why background processing is needed, retry/idempotency/failure strategy and deployment impact.

## M8.5 Deployment
Define dev/staging/production, Docker, HTTPS/reverse proxy, database backups, secrets, logs/monitoring, migration deployment, rollback, health checks and UAT. Do not let AI choose a cloud provider without company approval.

---

# 4. Daily Integration Questions
Before cross-domain merges, ask:
1. Did any DB table change?
2. Did any API contract change?
3. Did any shared enum/status change?
4. Did any business rule change?
5. Does another teammate depend on it?
6. Is there a migration?
7. Are docs updated?

If shared impact exists, sync before merge.

---

# 5. Universal Prompt Prefix
Paste before any future AI coding task:

```text
You are working on the KN Consumable ERP repository.
This is a production-oriented manufacturing ERP, not a demo.

Before doing anything:
1. Read the repository docs relevant to this task.
2. Follow docs/07_AI_BUILD_RULES.md.
3. Follow docs/08_TEAM_OWNERSHIP.md.
4. Respect docs/04_SYSTEM_ARCHITECTURE.md layer boundaries.
5. Do not invent business rules.
6. Mark unknown decisions TBD.
7. Do not modify another teammate's domain unless explicitly required.
8. Use Decimal/NUMERIC for precise business quantities.
9. Never put authoritative business calculations in React or FastAPI route handlers.
10. Do not add Celery/Redis unless this task explicitly approves it.

FIRST RESPONSE MUST BE PLAN ONLY. Do not edit files.
Return:
- understanding;
- dependencies;
- files;
- DB impact;
- API impact;
- security/permission impact;
- business-rule impact;
- tests;
- assumptions/TBD;
- cross-team impact.

STOP and wait for the exact word APPROVED.
```

---

# 6. Universal PR Checklist

```text
[ ] Scope completed
[ ] No invented business rules
[ ] Owner boundary respected
[ ] API contract documented
[ ] Migration reviewed
[ ] Decimal/NUMERIC correct
[ ] Backend authorization enforced
[ ] Audit added where required
[ ] Errors/edge cases handled
[ ] Unit tests pass
[ ] Integration/API tests pass where applicable
[ ] Frontend typecheck/build passes
[ ] Existing tests still pass
[ ] Real verification output reviewed
[ ] Cross-team impact communicated
[ ] Docs updated
[ ] Reviewer approved
```

---

# 7. Start Now — Exact Order

```text
TODAY
P0.1 repository + docs + branches

THEN IN PARALLEL
M1.1 Munees  — backend/database foundation
M1.2 Keerthi — frontend foundation
M1.5 Yathish — PRD/requirement contract design

AFTER M1.1
M1.3 Munees  — auth/RBAC backend

AFTER M1.2 + M1.3
M1.4 Keerthi — login/permission shell

PHASE 1 GATE

THEN IN PARALLEL
M2.1 Yathish — PRD import
M2.2 Keerthi — plant/process/route
M2.3 Munees  — consumable/unit/supplier

THEN
M2.4 Yathish — mappings

PHASE 2 GATE

THEN
Phase 3 Requirement + Plant Workflow
Phase 4 Inventory
Phase 5 Purchase/PO/GRN
Phase 6 Reports
Phase 7 Validation
Phase 8 Hardening
```

The first major business success criterion is:

```text
Real PRD
  ↓
Validated
  ↓
One approved consumable formula
  ↓
Correct calculated requirement
  ↓
Plant confirmation
  ↓
Final requirement
  ↓
Central stock
  ↓
Projected shortage
  ↓
Purchase recommendation
  ↓
Human approval
  ↓
PO
  ↓
GRN
```

Once one real consumable works completely through this vertical flow, expand rule types and categories.
