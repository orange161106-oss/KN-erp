# Performance and connection reliability — 2026-10-15

Owner: Munees. Scope: performance and technical reliability, preserving ERP formulas,
role/permission decisions, approval flows, central-stock authority and audit semantics.
Baseline source: develop commit 362c115. Changes are uncommitted for review.

## Findings and changes

The login entry previously imported every screen and the report-export libraries.
Routes now load their screen on demand, inside the existing permission gate and app
shell. A page-load failure has a recovery message instead of an uncaught blank page.
PDF/Word engines download only for the corresponding export action. Authentication
continues to use the backend and fresh database account/grant checks; no password or
permission-result cache was introduced, and hashing strength was not lowered.

Stock reads previously made separate metadata-user, class-count and total queries.
Eager metadata joins and combined aggregates reduce round trips while preserving
whole-batch summary/filter semantics. Bulk edits load reviewed row IDs together
after locking the batch, then validate and audit each change in the same transaction.
Period deletion, Decimal precision, missing/null values and source ownership are unchanged.

Large stock/PRD grids render the visible window plus an overscan region, with full
data retained for sorting, filtering, selection, copy/paste, undo and export.
Editing rows remain mounted while scrolling. Stock searches debounce at 300 ms;
pending search results block editing so they cannot discard an intervening draft.

Synchronous Excel parsing and SQL upload work had run inside async route handlers,
blocking unrelated requests on the event loop. Those handlers now use FastAPI's
worker-thread execution and UploadFile.file, retaining payloads, permissions, limits,
services and transactions. See [FastAPI concurrency guidance](https://fastapi.tiangolo.com/async/)
and [file handling](https://fastapi.tiangolo.com/tutorial/request-files/).

Pool defaults are now five retained plus five overflow per process, with separate
pool-wait/connect timeouts, LIFO, pre-ping, keepalives and 30-minute recycling.
A single remote connection warms before login traffic; test/loopback databases skip
it and connection failure remains recoverable. Operator settings are documented in
backend/README.md. Every worker/replica adds another pool: production sizing must
respect the provider's actual budget. No service plan or network route was changed.

Connection/schema/credential/capacity categories are logged without raw exceptions,
SQL, URLs or employee data. Authentication, health and read-only PRD preview have
bounded reconnect logic. The former preview handler disposed the whole engine and
retried all DBAPI errors; it now recovers only transient reads. A frontend GET may
retry an explicitly marked connection failure once; account switches/writes cancel
that recovery. Saves, login, receipts and deletions are never automatically repeated.
HTTP mutation errors explicitly disallow retry. Transaction recovery follows
[SQLAlchemy's disconnect boundary](https://docs.sqlalchemy.org/en/20/core/pooling.html#dealing-with-disconnects).

Large API responses negotiate gzip. Slow-request logs report registered route
templates, status and duration, without query strings, actual identifier values or
request bodies. A new read-only diagnostic checks latency and registered column
presence without migrating, seeding or editing business rows.

## Measurements

| Check | Baseline | Updated |
| --- | --- | --- |
| Initial entry JavaScript | Previously verified build, approximately 1.65 MB | 286.21 KB; 90.01 KB gzip |
| Reports page chunk | First split build: 864.72 KB | 18.09 KB; export engines download separately |
| Stock statement/management read, same creator/updater | 5 queries | 3 queries |
| 500-row statement/management save | 506 SELECTs | 5 SELECTs |
| 5,000-row stock grid | Rendered every row | Under 60 body rows in the initial test viewport |

Read counts and bulk-save counts compare baseline source retrieved from Git with
the changed services on isolated SQLite data. A separate comparison confirmed full
before/after read-response equality on the same 500-row data, including metadata,
records, Decimal/null values and aggregates. These are round-trip/DOM budgets, not
a production-user response-time benchmark or a PostgreSQL concurrency certificate.

The live read-only database probe on 2026-10-15 returned status `ok` and no missing
registered-model columns. Connection/round-trip samples were **6309 / 1025 / 24372 ms**.
Earlier samples were 4075 / 536 / 518 ms. This variation shows that remote/provider
latency remains material even for SELECT 1. The then-running backend health request
returned HTTP 200 with status/database `ok`; that single request took about 9.3 s.
Do not present the code improvements as proof that all live latency disappeared.

## Verification

- Final targeted backend run: **133 passed**, 5 existing deprecation warnings.
  Includes auth recovery/fresh grants, loading query budgets, new runtime tests,
  stock editing/deletion, stock/PRD imports, product-master and GRN/purchase workspaces.
  All fixtures use isolated SQLite or mocks; no live business data was altered.
- Full frontend suite: **114 passed, 17 files**. Includes bounded GET recovery,
  account/mutation invalidation, 5,000-row grid budgets, keyboard scrolling, exact
  edits and undo, debounced searches, permissions, deletion and existing screens.
- TypeScript build and Vite production build passed. Export libraries are separate
  chunks and the final build emitted no oversized-chunk warning.
- `uv lock --check` passed with 48 resolved packages. NumPy/pandas and the existing
  bcrypt requirement are now represented in the lockfile; package versions already
  locked for the rest of the backend were retained.
- `uv sync --frozen --extra test` completed successfully. Post-sync runtime/auth
  checks passed (27 tests); real Argon2 and legacy bcrypt allow/deny smoke checks
  passed with synthetic passwords, without logging hashes or credentials.
- `git diff --check` passed. This task adds no migration or business schema change.

Reproduce from backend with `python -m pytest` and the twelve files used in this
run: test_runtime_performance, test_auth_connection_recovery,
test_loading_performance, test_stock_grid_editing, test_stock_statement_delete,
test_stock_management_delete, test_stock_statement_import_resilience,
test_sales_schedule_import_resilience, test_phase4_product_master,
test_grn_workspace, test_prd_requirements_workspace and test_purchase_workspace
(all under app/tests, with .py suffix). Frontend: npm test; npm run build.

## Operational limits and follow-through

Restart the backend to adopt pool/warm-up settings and refresh the frontend to load
the new chunks. Deploy a production frontend build with suitable asset caching;
Uvicorn --reload and Vite dev mode are for development. Production capacity and
network/provider latency need validation in the intended hosting environment.

Connection recovery cannot guarantee service during an ISP/Supabase outage or repair
schema drift automatically. The diagnostic checks column presence, not index or
constraint correctness, migration ancestry, golden company cases or every business
integration. The two existing Alembic heads and previously recorded integration/
permission findings remain outside this optimization; do not blindly stamp/migrate.

The tracked .env.example contained credentials. It was replaced with blank variable
names; exposed database/signing credentials require operator rotation. Private .env
values were not modified and secrets are intentionally absent from this report.
