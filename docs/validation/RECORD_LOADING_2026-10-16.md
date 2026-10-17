# Record loading performance — 2026-10-16

Owner request: improve record loading across ERP components, especially Central
requirement plan and Existing monthly plans, preserving formulas, permissions,
approvals, source history and editing behavior.

## Agreed implementation scope

- Correct database pool-mode detection: Supabase session mode on port 5432 may
  reuse bounded application connections; transaction mode on 6543 retains NullPool.
  Respect existing configured size/overflow/wait/recycle settings. Provide an
  explicit mode override for operators using nonstandard proxy ports.
- Share initial Requirement page reads through additive workspace read endpoints;
  retain existing read/export endpoints and fresh server-side permission checks.
- Avoid requests for hidden screens and unnecessary per-keystroke remote searches.
- Do not cache completed permission/business responses, repeat writes, change
  manufacturing rules, mutate company records, or change database schema/provider.

The current session-pooler connection was incorrectly classified as transaction
mode by hostname alone. This discarded each application connection, ignored the
configured local pool budget, and discarded the startup warm-up connection.
Existing direct/session pool documentation already describes bounded reuse.
See [Supabase SQLAlchemy guidance](https://supabase.com/docs/guides/troubleshooting/using-sqlalchemy-with-supabase-FUqebT)
and [SQLAlchemy pool behavior](https://docs.sqlalchemy.org/en/20/core/pooling.html).

## Baseline

Read-only sample using the existing engine: NullPool, three connection/read timings
4,004 / 2,152 / 1,586 ms and four physical connections including the service read.
Central result services: 5,218 ms, 65 calculated lines, 159 configuration rows,
31 consumables. Monthly metadata/record services: 8,673 ms, 224 rows. These are
single observations with variable remote latency, not production capacity results.

## Verification

The mode correction is active in the running backend. Session/direct engines reuse
bounded connections with configured size, overflow, wait and recycling, LIFO,
pre-ping, keepalives and rollback on return. Transaction mode retains NullPool and
disabled prepared statements. `DB_POOL_MODE` permits an explicit proxy-mode override.
The diagnostic reports the actual pool type and does not claim a local connection
limit for NullPool.

Initial Central loading and post-save reload now use
`GET /api/v1/requirements/basic/workspace?planning_version_id=<optional UUID>`.
It returns available central revisions, selected_version_id and saved results.
The revision list now uses one query, preserving latest-across-all-revisions
semantics and including central history. Explicit invalid/noncentral selections
fail; an empty catalog returns no invented plan.

Monthly loading uses `GET /api/v1/requirements/workspace/view?month=...&year=...`
with existing search/plant/consumable/status filters. It returns records and
plan_metadata together, replacing two authenticated HTTP requests/connections.
Both additive APIs retain existing permission/central plant-scope checks and
response schemas. Existing read/export URLs remain available. No DB migration.

Production, monthly Requirement and Purchase searches wait 300 ms after typing,
with generation guards preventing obsolete results/errors from replacing the
current filter. Monthly Requirement and Purchase grids render visible rows through
the existing DataTable virtualization. Counts, full data, exports and formulas are
preserved. Norm imports, assembly preview and manual requirement upload execute
blocking parsing/database work in request workers, keeping unrelated requests free.

### Live read-only samples

| Measurement | Before | After |
| --- | --- | --- |
| Pool | NullPool | QueuePool |
| Three connection/read rounds, ms | 4004 / 2152 / 1586 | 4570 / 716 / 923 |
| Physical connections for those rounds and service read | 4 | 1 |
| Existing Central result services, ms | 5218 | 2618 |
| Existing monthly metadata/record services, ms | 8673 | 3948 |
| Calculated lines / diagnostics / consumables | 65 / 159 / 31 | 65 / 159 / 31 |
| Monthly row count | 224 | 224 |

First connection setup still pays the remote handshake; the backend warms and
retains one connection at startup. The after service reads in this sample were
approximately 50% / 54% shorter, not a guaranteed page-response SLA. No cached
business responses were used. Separate combined-loader samples took 4738 ms
(Central, including revision selection) and 5016 ms (monthly, metadata plus records),
and returned identical saved calculation IDs and quantities across views. These
are distinct samples/paths and include variable remote query latency.

The running backend returned three successful DB health responses in
776 / 1153 / 2124 ms; its OpenAPI document registers both new endpoints. No company
record was calculated, edited, deleted or approved during this performance task.

### Focused checks

- 90 backend checks passed: pool modes/budgets, combined read contracts, central and
  monthly quantities/access, import worker execution, norm/assembly/manual uploads
  and auth disconnect recovery. Disposable fixture data or mocks were used for
  mutations; live probes were read-only.
- 31 distinct frontend checks passed across central, monthly, production,
  loading and new search-generation checks. Initial Requirement loading is one
  HTTP request, post-save read failures do not repeat writes, and obsolete searches
  cannot overwrite current results/errors.
- TypeScript and Vite production build passed; `git diff --check` passed.
- Existing runtime fixtures were brought into line with current live stock-class
  derivation (seed an active catalog item and explicitly request all items for the
  all-item/gzip check), and current two-query parameter reads. Stock logic was not
  changed to satisfy old fixture assumptions.

Cross-team impact is technical: all screens share the corrected connection engine;
Requirement clients use additive read APIs; import handlers use worker execution.
Manufacturing rates/rounding, stock/purchase calculations, audit retention and
approval authority are unchanged. Actual production hosting/network capacity and
company configuration gaps still require their own evidence.
