# Roadmap

## M0 Foundation — Shared
- repo structure
- React bootstrap
- FastAPI bootstrap
- PostgreSQL
- SQLAlchemy/Alembic
- environment config
- common API errors
- auth foundation
- audit foundation
- test commands

## M1 Masters + PRD
Yathish: products, customers, PRD, mappings
Keerthi: plants, processes, routes
Munees: consumables, units, suppliers/constraints

## M2 Requirement
Yathish: rule framework + first deterministic rules + explanations/tests
Keerthi: confirmation/exception/approval
Munees: final-requirement handoff contract

## M3 Inventory
Munees: stock, projection, MSL, lead-time planning
Keerthi: shortage/MSL alerts
Yathish: time-phased requirement contract if required

## M4 Purchase
Munees: net requirement, MOQ/pack/multiple, recommendations
Keerthi: approval/notification workflow
Yathish: requirement-version traceability

## M5 PO + GRN
Munees: PO, pending PO, GRN, inventory update
Keerthi: due/delay alerts and approval visibility

## M6 Validate Against Existing Excel
All: use representative consumables and investigate differences.
Never force ERP to match a known-wrong Excel result.

## M7 Reports/Dashboard
- plant plan
- material plan
- supplier purchase plan
- pending PO
- MSL/shortage
- planned vs actual
- summary plan
- management dashboard

## M8 Production Hardening
- permission review
- concurrency testing
- backup/recovery
- logging
- performance
- deployment
- UAT
