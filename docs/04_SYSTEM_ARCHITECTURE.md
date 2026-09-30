# System Architecture

## Business flow

```text
KN SaaS ERP
   ↓ Excel/CSV
Import → Staging → Validation
   ↓
PRD / Production Data
   ↓
Requirement Calculation Engine
   ↓
Plant Confirmation / Exceptions / Approval
   ↓
Final Requirement
   ↓
Central Inventory + Confirmed Incoming PO
   ↓
Inventory Planning Engine
   ↓
Projected Stock + MSL + Lead Time
   ↓
Purchase Planning Engine
   ↓
Purchase Recommendation
   ↓
Human Approval
   ↓
PO
   ↓
GRN
   ↓
Central Store
```

## Software layers

```text
React UI
   ↓
FastAPI API
   ↓
Application/Service Layer
   ↓
Domain Layer
   ├─ Requirement Engine
   ├─ Inventory Engine
   ├─ Purchase Engine
   ├─ Approval Policies
   └─ Alert Policies
   ↓
Repository Layer
   ↓
SQLAlchemy
   ↓
PostgreSQL
```

## Layer rules
### React
May render, collect input and call APIs.
Must not calculate authoritative requirements/purchases or access DB directly.

### FastAPI routes
May authenticate, authorize, validate schemas, call services and serialize responses.
Must not contain manufacturing formulas.

### Application services
Coordinate transactions, repositories, engines, approvals and audit.

### Domain layer
Contains deterministic business rules and must be independently testable.

### Repository/data layer
Persistence only. Do not hide business rules in ORM queries.

## Backend structure

```text
backend/app/
  api/
  modules/
    auth/
    masters/
    prd/
    requirements/
    plant_workflow/
    inventory/
    purchasing/
    po_grn/
    alerts/
    reports/
  domain/
    requirement_engine/
    inventory_engine/
    purchase_engine/
  services/
  repositories/
  models/
  schemas/
  db/
  security/
  workers/
  tests/
  main.py
```

## Frontend structure

```text
frontend/src/
  app/
  components/
  features/
    auth/
    masters/
    prd/
    requirements/
    plants/
    inventory/
    purchasing/
    po-grn/
    alerts/
    reports/
  hooks/
  services/
  types/
  utils/
```
