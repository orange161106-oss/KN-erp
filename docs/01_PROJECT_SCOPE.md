# Project Scope

## Goal
Build a standalone web-based Consumable Planning ERP for KN.

The ERP must calculate approved consumable requirements, support plant confirmation and exceptions, manage central-store inventory, predict shortages, recommend purchases, track PO/GRN, generate alerts, preserve audit history, and provide reports.

## Existing company ERP
KN already has a SaaS ERP that handles raw-material planning accurately.

This project:
- does not replace the raw-material ERP;
- initially assumes no direct API/database access;
- may consume standardized Excel/CSV exports;
- may later replace the file connector with an approved API connector.

## In scope
- Authentication and RBAC
- Master data
- PRD/production import
- Excel staging/validation
- Product → Plant mapping
- Route/process mapping
- Product/process → Consumable mapping
- Consumption/business-rule master
- Requirement Calculation Engine
- Plant confirmation
- Additional/exception requirements
- Approval workflow
- One central consumable store
- Stock transactions/reconciliation
- MSL
- Lead time
- Projected inventory
- Reorder logic
- Supplier master
- MOQ, pack size, order multiple
- Purchase recommendation
- PO
- GRN
- Pending PO
- Alerts
- Audit trail
- Planned vs actual/history
- Excel import/export
- Reports/dashboard

## Out of scope for Phase 1
- Rebuilding raw-material ERP
- AI/ML/LLM inside ERP decision logic
- automatic norm changes without human approval
- unapproved direct writes to SaaS ERP
- microservices/Kafka/Kubernetes
- predictive AI purchasing
- multi-company SaaS
- machine/manpower capacity unless later approved

## Core engines
1. Requirement Calculation Engine
2. Inventory Planning Engine
3. Purchase Planning Engine
