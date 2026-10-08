# ERP loading improvements — 8 October 2026

## Findings and changes

Every authenticated request previously loaded the user, roles and role permissions
in three separate database queries. These now load in one joined query. Account
activity and grants are still read on each request; they are not cached.

The Products list previously reflected database metadata before reading products.
It made four queries on the measured PostgreSQL database. It now makes one data
query and translates missing-table/missing-column errors into the existing
actionable setup error. The write-path schema checks are retained.

Production Mapping now loads product choices and the visible traceability view
first. Mapping lists and consumable choices load when their tabs are opened.
Failed tab requests can be retried. An older resolution response cannot overwrite
a newer product selection.

The shared browser client deduplicates simultaneous GET requests, including
StrictMode effects and repeated unit-name lookups. Completed responses are not
cached. Changing authentication or writing data clears shared pending reads.
Master searches wait for a 300 ms typing pause.

Mapping resolution and integrity validation load products, plants/routes, process
steps and consumable mappings in batches. Validation uses at most four data
queries rather than querying inside product/plant/step loops. Resolution uses at
most five, including units. Route lists fetch all their steps together.

## Read-only measurements

The configured database contains 594 products. Measurements used the real
configured database without modifying its data, grants or schema. They measure
backend service calls, not complete authenticated browser page loads. Each
measurement also includes connection checkout, a read-only transaction setup and
session cleanup. The benchmark prints no account data, credentials or query text.

| Operation | Before | After |
| --- | --- | --- |
| Permission lookup | 3 SQL statements; 2.969 s sample | 1 statement; samples 1.609–5.422 s |
| Products | 4 SQL statements; 5.125 s sample | 1 statement; samples 0.765, 8.609 and 1.437 s |
| All-product mapping audit | Existing loop queried plant mappings separately for every active product | 2 statements for the current unmapped data; samples 0.953–2.968 s |

The lower statement counts are repeatable. Elapsed-time improvements are not
guaranteed: the repeat run had a slow 8.609 s Products read despite using one query.
The final Products operation itself took 0.453 s, with 1.437 s total lifecycle time.
The permission operation also experienced a slow 4.312 s single-query read.
Network/pooler/database response variability remains a separate bottleneck.

The configured Supabase session pooler hostname identifies region
`ap-northeast-2` (Seoul); the application runs locally. Physical distance can
contribute to latency, but these measurements do not isolate the cause of every
slow response. Supabase recommends choosing a region close to users:
https://supabase.com/docs/guides/platform/regions

## Verification

- 43 backend loading, permission and product-batch tests passed using isolated
  SQLite databases. They cover grant revocation, overlapping roles, schema errors,
  multi-plant resolution, inactive entities and 600-product audit query counts.
- The complete frontend suite passed: 58 tests before the final retry addition.
  All 8 loading-performance tests passed after adding the mapping retry test.
- Frontend production build passed. The existing single-bundle size warning remains.
- Lint passed for all changed frontend files, including the final retry addition.
- The running backend was confirmed to have automatic code reload enabled.

`backend/scripts/benchmark_loading.py` can repeat the read-only measurements.
