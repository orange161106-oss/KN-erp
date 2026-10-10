# Database and API Rules

## Database rules
- PostgreSQL is system of record.
- SQLAlchemy handles persistence.
- Alembic handles schema migrations.
- Never edit a migration already merged/applied in shared environments.
- Store timestamps in UTC.
- Use `NUMERIC`/`Decimal` for precise values.
- Do not hard-delete important transactional/audit history.
- Use transactions/locking/version checks for stock, approval, PO and GRN races.

## Core entity groups
Security:
- users, roles, permissions

Masters:
- plants, customers, products, processes
- routes, route_steps
- consumables, units
- suppliers, supplier_consumables
- business_rules/consumption_norms

Planning:
- planning_versions
- prd_orders, prd_order_items
- calculated_requirements
- plant_requirements
- requirement_adjustments
- approvals

Inventory/Purchase:
- stock_transactions
- inventory snapshot/balance strategy
- purchase_recommendations
- purchase_orders/items
- grns/items

Governance:
- alerts
- audit_logs
- import_batches
- import_errors

## Traceability
Calculated records must answer:
- which planning version?
- which PRD source?
- which business-rule version?
- which stock snapshot?
- which supplier constraint?
- which user adjustment/approval?

## API
Prefix: `/api/v1/`

Use Pydantic request/response schemas.
Never expose ORM entities directly.
Backend authorization is mandatory; hiding a React button is not security.

Consistent error shape:

```json
{
  "code": "MISSING_CONSUMPTION_RULE",
  "message": "No approved consumption rule exists for this mapping.",
  "details": {}
}
```

Breaking API changes require docs, frontend coordination and tests.
