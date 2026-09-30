# Munees — Inventory & Purchase Domain

## Mission
Own the flow from approved final requirement to stock planning, reorder, purchase recommendation, PO, GRN and related reports.

## Owned areas
- inventory
- purchasing
- PO/GRN
- supplier constraints
- central-stock planning

## Engines
- Inventory Planning Engine
- Purchase Planning Engine

## Inputs
From Yathish:
- requirement/planning version
From Keerthi:
- approved adjustments/final workflow state

## Outputs
To Keerthi:
- shortage/MSL/PO-delay events
- approval items
To reports:
- stock/projection/purchase/PO/GRN/supplier plans

## AI boundary
Do not change Requirement Engine formulas or plant approval behavior without an agreed cross-team contract.
