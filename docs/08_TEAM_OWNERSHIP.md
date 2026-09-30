# Team Ownership

Split by business domain, not by technical layer.

Each teammate owns the vertical slice: schema + backend + frontend + tests + docs for that domain.

## Munees — Inventory & Purchase Planning
Owns:
- consumable/unit/supplier master coordination
- central inventory
- opening stock
- stock transactions/reconciliation
- pending PO
- MSL
- supplier lead time
- projected inventory
- reorder logic
- target stock
- net requirement integration
- MOQ
- pack size
- order multiple
- purchase requirement/recommendation
- purchase approval integration
- PO
- GRN
- supplier/material purchase reports

Core engines:
- Inventory Planning Engine
- Purchase Planning Engine

## Keerthi — Plant Workflow, Access & Alerts
Owns:
- plant master
- process/route coordination
- plant-based access
- plant requests
- confirmation workflow
- exception/additional request workflow
- approvals workflow
- plant issue workflow
- emergency MSL draw workflow if approved
- local/floor stock only if KN confirms it
- inter-plant transfer only if KN confirms official plant stocks/transfers
- RBAC workflow coordination
- alerts
- dashboard/workflow visibility

## Yathish — Production & Requirement Calculation
Owns:
- customer/product masters
- Product → Plant mapping
- PRD/production import domain
- PRD validation
- child-part/BOM if confirmed
- production quantity derivation
- product/process → consumable mapping
- norms/business-rule master
- rule-type configuration
- production/area/packing/tool-life/fixed/plant-request rules
- Requirement Calculation Engine
- planning versions
- plant-wise calculated requirement
- material-wise requirement
- summary requirement

## Cross-domain flow

```text
Yathish: Calculated Requirement
          ↓
Keerthi: Plant Confirmation / Approval
          ↓
Munees: Inventory + Purchase Planning
          ↓
Keerthi: Alerts / Workflow Visibility
```

## Shared changes
For shared models/contracts:
1. update/agree docs first
2. agree schema/API
3. implement
4. update tests

A teammate may consume another domain's public contract, not rewrite its internal logic.
