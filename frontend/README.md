# KNL Consumable ERP frontend

React + TypeScript + Vite. M2.3 adds units, consumables, suppliers and supplier mappings.
The shared contract is [master-data contract](../docs/15_CONSUMABLE_SUPPLIER_MASTER_CONTRACT.md).
Actual validation and reviewer notes are in [M2.3 handoff](../backend/M2_3_REVIEW.md).

## Run locally

Use a current Node version supported by the locked Vite/Vitest packages (Node 22.12+
with a compatible current patch or Node 24+). From this directory:

```powershell
npm ci
npm run dev
```

Run FastAPI on `127.0.0.1:8000` after configuring your ignored backend `.env` and
running `alembic upgrade head`. Vite proxies relative `/api` requests to that backend.
The API client defaults to the same origin. `VITE_API_BASE_URL` can override it when
an approved deployment provides the matching network/CORS configuration. No signing
secret, database URL or password belongs in frontend environment variables.

A production deployment must serve the frontend and proxy `/api` to FastAPI over
HTTPS; Vite's development proxy is not a production server. `npm run preview` serves
build assets for inspection and does not provide the development API proxy.

## Authentication and permissions

Login uses `/api/v1/auth/login`, then loads `/api/v1/auth/me`. Use a provisioned ERP
account, not PostgreSQL credentials. The database migration creates no default ERP
accounts and assigns no role grants. Approved operator provisioning is a prerequisite.

Access tokens remain in memory. Reload/logout clears them; 401 clears authentication
and returns to login. Master navigation and mutation buttons use the backend's
permission codes; backend authorization remains authoritative. ADMIN is not a
master-permission shortcut. Existing unrelated navigation retains its prior role-based
presentation and is not an authorization guarantee.

## Master screens

Masters includes Units, Consumables and Suppliers. Supplier details manage consumable
mappings. Lists support search, pagination and active/inactive/all filters. Forms
require a reason, show server errors and select active references. Inactivation retains
IDs/history. Consumable unit names and mapping names require the relevant read grants.
No purchase/stock calculation or unapproved numeric supplier fields are present.

## Validation

```powershell
npm test
npm run build
npm run lint
```

Vitest + Testing Library cover login/logout, token handling, 401/403, read-only access,
create/edit/status forms, inactive filtering/reactivation, units and supplier mappings.
Build includes the TypeScript check. Tests use synthetic responses, no real accounts.

## Central inventory (M4.1)

Inventory navigation requires `inventory.stock.read`. The screen presents dated
usable balances, missing-import state, material/movement/time history filters,
exact four-place quantities and explicit source-unit conversion. It does not
contain warehouse posting, reservation, opening or adjustment forms. Issues are
dispatches, not automatically actual consumption. Source import is available only
to `inventory.stock.import` holders while backend imports are enabled; submitting
the same export again reports replay without duplicating rows. Backend enforcement
is authoritative. See the [inventory contract](../docs/17_CENTRAL_INVENTORY_CONTRACT.md)
and [M4.1 handoff](../backend/M4_1_REVIEW.md). Real export mapping remains TBD.
