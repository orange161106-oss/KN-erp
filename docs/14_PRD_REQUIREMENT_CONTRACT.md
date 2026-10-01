# M1.5 PRD and Requirement Domain Contract

Owner: Yathish. Reviewer: Munees. Approved implementation plan: M1.5.  
Branch: `feature/yathish/m1.5-prd-requirement-contract`.

---

## 1. Domain Objective & Boundaries

The **Production & Requirement Domain** is responsible for transforming raw production planning data (PRD) into deterministic, explainable, plant-specific calculated consumable requirements.

```text
KN SaaS ERP PRD Export (.xlsx)
        ↓
Staging & Validation (M2.1)
        ↓
Canonical PRD Items + Planning Version (M2.1)
        ↓
Mapping Resolution: Product → Plant → Route/Process → Consumable (M2.4)
        ↓
Approved Consumption Norm / Rule Selection (M3.1 / M3.2)
        ↓
Requirement Calculation Engine (M3.3)
        ↓
Calculated Requirements with Deterministic Explanation
        ↓
[ Handoff to Plant Workflow — Keerthi (M3.4 / M3.5) ]
```

### Strict Boundaries (What this Domain DOES NOT do):
- **NO Inventory / Purchase Concepts**: Does not track stock balances, MSL, incoming POs, lead times, safety stocks, or purchase quantities (owned exclusively by Munees in M4).
- **NO Invented Fields**: Does not introduce speculative spreadsheet columns or company fields not confirmed by KN.
- **NO Unapproved Formulas**: Does not hardcode ad-hoc formulas or heuristics based on consumable names.
- **NO Direct In-place Editing of Calculated Demand**: Plant users cannot overwrite engine-calculated quantities; additions are separate traceable records (M3.4).

---

## 2. Canonical PRD Schema Proposal

Excel data from KN's SaaS ERP export must never become active planning data directly. The ingestion pipeline separates **Staging** from **Canonical Planning Items**.

### 2.1 Staging Contract (`prd_staging_items`)
Holds raw row data as uploaded, before validation.

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `UUID` | Primary key |
| `import_batch_id` | `UUID` | FK to import batch / upload audit record |
| `source_row_number` | `Integer` | Physical Excel row index (1-based) |
| `raw_data` | `JSONB` | Key-value pairs of raw spreadsheet column strings |
| `validation_status` | `Enum` | `PENDING`, `VALID`, `INVALID` |
| `error_code` | `String` | e.g. `UNKNOWN_PRODUCT`, `UNKNOWN_PLANT`, `INVALID_QUANTITY`, `DUPLICATE_ROW` |
| `error_details` | `JSONB` | Field-specific validation failures |

### 2.2 Canonical PRD Item Contract (`prd_order_items`)
Only records passing 100% of staging validations are promoted into the canonical PRD domain table for a specific `planning_version`.

| Field | Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `UUID` | PK, Default UUIDv4 | Unique line identifier |
| `planning_version_id` | `UUID` | FK `planning_versions.id`, NOT NULL | Associated planning cycle revision |
| `source_row_number` | `Integer` | NOT NULL | Source row number in imported workbook |
| `product_code` | `VARCHAR(64)` | NOT NULL | Product code from PRD |
| `product_id` | `UUID` | FK `products.id`, NOT NULL | Resolved Product Master reference |
| `plant_code` | `VARCHAR(32)` | NOT NULL | Target manufacturing plant code |
| `plant_id` | `UUID` | FK `plants.id`, NOT NULL | Resolved Plant Master reference |
| `planned_quantity` | `NUMERIC(14, 4)`| CHECK (`planned_quantity > 0`) | Planned production quantity (Decimal) |
| `uom` | `VARCHAR(16)` | NOT NULL | Production unit (e.g., `PCS`, `NOS`) |
| `target_period` | `VARCHAR(7)` | NOT NULL, format `YYYY-MM` | Planning period / month |
| `customer_code` | `VARCHAR(64)` | NULLABLE | Customer identifier (TBD pending sample) |
| `customer_id` | `UUID` | FK `customers.id`, NULLABLE | Resolved Customer reference (if in PRD) |
| `created_at` | `TIMESTAMPTZ` | UTC, NOT NULL | Import timestamp |
| `updated_at` | `TIMESTAMPTZ` | UTC, NOT NULL | Modification timestamp |

**Integrity Constraints**:
- `UNIQUE (planning_version_id, product_id, plant_id, target_period)`: Prevents accidental duplicate rows for the same product at the same plant within a planning version.
- `planned_quantity > 0`: Zero or negative quantities are rejected during staging.
- No auto-creation of missing products or plants; unmapped entries fail validation.

---

## 3. `planning_version` Concept

Per Project Rule 46: *"Planning revisions are records/versions. Never hard-code R1/R2 as permanent columns."*

A `planning_version` represents an immutable cycle revision of the production plan for a specific horizon (e.g. October 2026 Revision 0 vs Revision 1).

### 3.1 Model Attributes (`planning_versions`)

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `UUID` | Primary Key |
| `planning_period` | `VARCHAR(7)` | Target horizon (e.g., `2026-10` for Oct 2026) |
| `version_number` | `Integer` | 0, 1, 2... (monotonic increment per period) |
| `revision_label` | `VARCHAR(16)` | `R0`, `R1`, `R2`... human-readable label |
| `description` | `TEXT` | Optional change rationale / notes |
| `source_filename` | `VARCHAR(255)`| Filename of the imported PRD workbook |
| `status` | `Enum` | Version lifecycle status (see below) |
| `created_by` | `UUID` | FK `users.id` (Planner who uploaded) |
| `created_at` | `TIMESTAMPTZ` | UTC creation timestamp |
| `locked_at` | `TIMESTAMPTZ` | Timestamp when PRD was frozen for calculation |
| `calculated_at`| `TIMESTAMPTZ` | Timestamp when calculation completed |
| `approved_at`  | `TIMESTAMPTZ` | Timestamp when final plan was approved |
| `approved_by`  | `UUID` | FK `users.id` (Approver) |

### 3.2 Planning Version Lifecycle
```text
[ DRAFT ] ────────► [ VALIDATED ] ────────► [ LOCKED ] ────────► [ CALCULATING ]
   │                       │                    │                       │
   │ (upload fails)        │ (validation err)   │ (cancel)              │ (rule error)
   ▼                       ▼                    ▼                       ▼
[ REJECTED ]            [ REJECTED ]         [ CANCELLED ]    [ CALCULATION_FAILED ]
                                                                        │
                                                                        ▼
[ RELEASED_TO_PLANTS ] ◄───────────────────────────────────────── [ CALCULATED ]
        │
        ├────────► [ UNDER_PLANT_REVIEW ]
        │                  │
        │                  ▼
        ├────────► [ PLANTS_CONFIRMED ]
        │                  │
        │                  ▼
        └────────► [ FINAL_APPROVED ] ────────► Handed off to Munees (Inventory/Purchase)
                           │
                           ▼ (if superseded by new revision R1)
                     [ SUPERSEDED ]
```

### 3.3 Immutability & Recalculation Rules
1. **Draft Recalculation**: While in `DRAFT` or `CALCULATED` (prior to `RELEASED_TO_PLANTS`), recalculation is **idempotent**: previous calculated records for this version are cleanly replaced.
2. **Post-Release Immutability**: Once a version is `RELEASED_TO_PLANTS`, its PRD items and calculated requirements become strictly **immutable**.
3. **Revisions (R0 → R1)**: If production figures change after release, the planner creates a new version (`version_number = 1`, `revision_label = 'R1'`). The prior version moves to `SUPERSEDED` upon approval of the new revision.

---

## 4. Required Identifiers (Entity IDs)

Every calculated requirement row must trace back to the following 6 core identifiers:

1. **`planning_version_id` (`UUID`)**: Isolates requirements to a specific planning period and revision cycle.
2. **`product_id` (`UUID`)**: Identifies the manufactured part/assembly from Product Master.
3. **`plant_id` (`UUID`)**: Identifies the specific manufacturing plant/factory incurring the demand.
4. **`process_id` (`UUID`)**: Identifies the route operation step (e.g., Welding, Powder Coating, Final Packing).
5. **`consumable_id` (`UUID`)**: Identifies the specific consumable required from Consumable Master.
6. **`business_rule_id` (`UUID`)** + **`rule_version` (`Integer`)**: Identifies the exact approved consumption norm and rule revision applied.

---

## 5. Calculated Requirement Output Contract

The Requirement Calculation Engine evaluates canonical PRD rows against approved mapping chains and norms, writing records to `calculated_requirements`.

### 5.1 Schema (`calculated_requirements`)

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | `UUID` | Primary Key |
| `planning_version_id` | `UUID` | FK `planning_versions.id`, indexed |
| `prd_item_id` | `UUID` | FK `prd_order_items.id` (source line traceability) |
| `product_id` | `UUID` | FK `products.id`, indexed |
| `plant_id` | `UUID` | FK `plants.id`, indexed |
| `process_id` | `UUID` | FK `processes.id` / route step, indexed |
| `consumable_id` | `UUID` | FK `consumables.id`, indexed |
| `business_rule_id` | `UUID` | FK `business_rules.id` |
| `rule_version` | `Integer` | Snapshot version of rule at execution time |
| `source_production_qty` | `NUMERIC(14, 4)` | Production quantity driving the requirement |
| `calculated_qty` | `NUMERIC(14, 4)` | Exact mathematical requirement before rounding |
| `rounded_qty` | `NUMERIC(14, 4)` | Authoritative calculated requirement after approved rounding |
| `uom_id` | `UUID` | Consumable Unit of Measurement (FK `units.id`) |
| `status` | `Enum` | `CALCULATED`, `PENDING_CONFIRMATION`, `CONFIRMED`, `EXCEPTION_ATTACHED`, `SUPERSEDED` |
| `explanation` | `JSONB` | Complete, deterministic calculation breakdown |
| `calculated_at` | `TIMESTAMPTZ` | UTC execution timestamp |
| `calculated_by` | `UUID` | FK `users.id` (system or user trigger) |

### 5.2 Aggregation Views Exposed to Other Modules
- **Plant-Wise Material Requirement**:
  `SUM(rounded_qty)` grouped by `(planning_version_id, plant_id, consumable_id)`.
- **Company-Wide Central Store Requirement**:
  `SUM(rounded_qty)` grouped by `(planning_version_id, consumable_id)`.

---

## 6. Calculation Explanation Structure

Per Project Rule 8: *"Every calculation must be explainable from stored inputs and rule parameters."*  
No calculations may occur via opaque or unrecorded logic.

The `explanation` field is stored as a validated JSON object matching the following structure:

```json
{
  "rule_type": "AREA_COVERAGE",
  "rule_id": "b7d8e870-761a-4d22-b5e0-82d2f70275da",
  "rule_version": 1,
  "formula_name": "Powder Coating Area Coverage Norm",
  "formula_expression": "raw_qty = (production_qty * area_per_unit_sqm) / coverage_per_kg * (1 + waste_pct/100)",
  "parameters": {
    "area_per_unit_sqm": "1.7500",
    "coverage_per_kg": "8.5000",
    "waste_allowance_pct": "5.0000"
  },
  "source_inputs": {
    "product_code": "BRACKET-XYZ",
    "plant_code": "PLANT-1",
    "production_qty": "500.0000",
    "production_uom": "PCS"
  },
  "steps": [
    {
      "step_number": 1,
      "description": "Calculate total painted surface area",
      "formula": "500.0000 PCS * 1.7500 m2/unit",
      "result": "875.0000",
      "uom": "SQM"
    },
    {
      "step_number": 2,
      "description": "Calculate base powder consumption at standard coverage rate",
      "formula": "875.0000 SQM / 8.5000 m2/kg",
      "result": "102.9412",
      "uom": "KG"
    },
    {
      "step_number": 3,
      "description": "Add approved 5% process waste allowance",
      "formula": "102.9412 KG * 1.05",
      "result": "108.0882",
      "uom": "KG"
    }
  ],
  "raw_result": "108.0882",
  "rounding_policy": {
    "method": "ROUND_HALF_UP",
    "decimal_places": 2,
    "rounding_increment": "0.01"
  },
  "final_qty": "108.09",
  "consumable_uom": "KG"
}
```

### Initial Rule Types Covered:
- `PRODUCTION_RATE`: `production_qty * consumption_rate`
- `AREA_COVERAGE`: `(production_qty * area_per_unit) / coverage`
- `PACKING_RATIO`: `production_qty / units_per_pack`
- `TOOL_LIFE`: `(production_qty * operations_per_unit) / tool_life_operations`
- `FIXED_QUANTITY`: Constant setup/batch requirement
- `PLANT_REQUEST`: Handled via plant exception workflow, not auto-calculated
- `MAINTENANCE`: Maintenance cycle norm
- `MIN_MAX`: Inventory safety buffer norm

---

## 7. Statuses Needed for Handoff to Plant Workflow

Keerthi owns the Plant Workflow (M3.4 / M3.5). The handoff contract between Requirement Engine and Plant Workflow is defined as follows:

### 7.1 Handoff Pre-conditions
The Requirement Engine hands off to Plant Workflow **only when**:
1. `planning_version.status == RELEASED_TO_PLANTS`.
2. All canonical PRD items have resolved mappings and valid calculated requirements (0 calculation errors).
3. The planning version is locked from further PRD modifications.

### 7.2 Requirement Item Status Lifecycle
| Status | Meaning | Actor |
| :--- | :--- | :--- |
| `CALCULATED` | Engine finished calculation; internal to planning domain. | Requirement Engine |
| `PENDING_CONFIRMATION`| Available on Plant In-charge dashboard for review. | System on Release |
| `CONFIRMED` | Plant In-charge reviewed and accepted calculated quantity. | Plant In-charge |
| `EXCEPTION_ATTACHED` | Plant In-charge accepted calculated baseline but logged an additional requirement. | Plant In-charge |
| `SUPERSEDED` | Superseded by subsequent planning revision. | System |

### 7.3 Immutability of Calculated Quantities
- `calculated_requirements.calculated_qty` and `rounded_qty` are strictly **read-only** for plant users.
- Plants **cannot** edit the calculated quantity.
- Additional plant needs (special project, rework, maintenance) are submitted as separate `plant_requirement_exceptions` records referencing `calculated_requirement_id`.

### 7.4 Final Requirement Contract for Munees (Phase 4)
When M3.5 completes approval:
$$\text{Final Requirement} = \sum (\text{calculated\_requirements.rounded\_qty}) + \sum (\text{approved additional\_qty})$$
Only additions with status `APPROVED` are included. Rejected or pending additions are excluded.

---

## 8. Explicit TBD List

The following items are unresolved business/technical decisions requiring confirmation with KN stakeholders and teammates:

- **TBD-1: Real PRD Workbook Column Specifications**:
  Exact spreadsheet layout from KN's SaaS ERP is not yet in the repository. We need confirmation of:
  - Header names (e.g. `Part No`, `Description`, `Plant`, `Qty`, `Month`).
  - Whether Customer Code, Work Order Number, Model, Drawing No, or Delivery Dates are present.
- **TBD-2: Multi-Plant Allocation Logic**:
  Does the PRD export explicitly define the manufacturing `plant_code` for every single line item? If a product is manufactured across multiple plants without plant designation in the file, what allocation rule applies?
- **TBD-3: Finished Assembly vs Child Parts (BOM Level)**:
  Does the SaaS ERP export contain finished product part numbers only, or already exploded component/child parts? If finished products only, is child-part BOM explosion required before consumable mapping?
- **TBD-4: First Golden Rule Selection for M3.2**:
  Which consumable and product will serve as the First Golden Rule? (Recommendation: Corrugated Box via `PACKING_RATIO` or Powder Coating via `AREA_COVERAGE`. CO2 is excluded per execution guide until KN confirms formula).
- **TBD-5: Rounding Norm Standards per Material Type**:
  Should rounding increments be stored at the Consumable Master level (e.g., Gas Cylinders = integer ceil; Chemicals = 2 decimal places; Granules = 25kg bag increments), or at the Business Rule level?
- **TBD-6: Plant Confirmation SLA & Partial Finalization**:
  If Plant 1 confirms its requirements but Plant 2 delays, can Central Store / Purchase planning begin for Plant 1 consumables, or is handoff strictly atomic per planning version?
- **TBD-7: Revision Conflict Handling (R0 → R1)**:
  When a revision R1 is imported after Plant In-charges have already entered confirmations/exceptions on R0, what is the policy for migrating or invalidating those plant exceptions?
