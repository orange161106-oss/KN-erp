# Yathish — Production & Requirement Domain

## Mission
Transform PRD/production data into explainable calculated consumable requirements.

## Owned areas
- PRD
- products/customers
- product → plant
- BOM/child parts if confirmed
- mapping/rules/norms
- planning versions
- requirement calculations

## Engine
Requirement Calculation Engine

## Initial rule types
PRODUCTION_RATE, AREA_COVERAGE, PACKING_RATIO, TOOL_LIFE, FIXED_QUANTITY, PLANT_REQUEST, MAINTENANCE, MIN_MAX

Only implement approved formulas.

## Calculation output must explain
- planning version
- product/plant/process/consumable
- rule type/version/parameters
- source production qty
- steps
- raw result
- rounding
- final calculated requirement

## AI boundary
Do not invent stock, MSL, lead-time, purchasing or approval rules.
