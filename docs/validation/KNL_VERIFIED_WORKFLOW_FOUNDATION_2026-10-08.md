# Verified workflow foundation — 8 October 2026

Owner: Munees. Cross-team review: Keerthi (security/approval), Yathish (PRD/calculation).
Status: local implementation for review, not a production release or full workbook
parity certification. The approved Supabase schema/checkpoint recovery below has
been applied. Business records were not changed. No commits, pushes or merges
were performed by this implementation.

## Delivered

### Shared database recovery finding

The configured database was inspected read-only after a product save returned 500.
Its `products` table lacked `item_id` and `part_number`. Its migration marker was
`2994bb185290`, absent from the checkout and refreshed remote Git history. Ten
external Boolean `users.can_access_*` columns are present. There is one Super Admin
and no product records at inspection time. These are environment observations,
not changes applied to the database.

`python -m app.db.recover_product_setup` is a read-only preflight for this exact
schema. It passed. `--apply` requires explicit shared-database recovery approval:
it locks relevant tables, verifies the schema, saves schema/checkpoint evidence
under ignored `.local/migration-recovery`, reconciles the marker to the verified
known baseline `ee17a6e77f73`, and applies migrations 0020 and 0021 in one transaction.
It preserves the ten external access columns and all business records. The local
schema/checkpoint evidence is not a full backup of business data. This reconciles a
checkpoint; it does not recover or claim to reconstruct the missing migration file.
After the owner explicitly approved database repair, `--apply` completed and
committed. A fresh connection verified `0021 (head)`, both product columns, all ten
preserved external access columns, and the Super Admin unique index. Product listing
succeeded with zero records; the repair did not import products. Schema/checkpoint
evidence is in `.local/migration-recovery/product-setup-20261008T081923871469Z.json`.
All 45 isolated backend tests passed before applying the recovery.
Product APIs also return an actionable 503 setup error for unmigrated databases
instead of querying missing identifier columns and returning a generic 500.

### Product upload follow-up

Batch-save performance follow-up: reviewed products previously performed one
existing-code query per row. Saving now validates all input first, loads existing
codes once, inserts new products with RETURNING, and inserts their audit records
in the same transaction. The 593-row isolated test verified one product lookup,
one product insert batch and one audit insert batch. Matching replays add no new
audit records; conflicting data and audit failures roll back. All 48 backend
tests, three Products frontend tests and TypeScript checks passed. No live import
was submitted to benchmark the change. Read-only checks after the user's save
found 594 committed products and 594 product creation audit records matching the
uploaded workbook hash. Live elapsed save time has not been benchmarked.

Read-only preview of `prd.ord.xlsx` now finds 593 product identities. All 593
need explicitly reviewed production units. Source rows 531 and 540 share the same
Item ID and Part No. but have different descriptions. Preview retains both source
descriptions and leaves the master description blank until the operator chooses
one; it does not silently merge their meaning or write any masters.

Masters now opens Products by default. The upload panel shows progress, prominent
errors, product count and conflict choices. A 30-second preview connection timeout
provides feedback when the backend does not respond. Saving still requires a
reviewed identifier, description and production unit for every candidate.

Follow-up validation: 12 isolated backend workflow tests, 50 frontend tests,
TypeScript check, production build and whitespace check passed. The actual workbook
was parsed without database writes. This validation preceded the separately approved
shared database recovery recorded above.

- Shared permission policy maps the ten feature checkboxes to corresponding backend
  operations. False flags override old grants for mapped operations. Base roles are
  labels and do not bypass these checks. PRD mutation requires both planning-view
  and calculation flags; read-only planning requires planning-view alone.
- Operations absent from the ten-checkbox matrix retain explicit legacy permission
  requirements: stock read/import, projection import/read, PO pricing/cancellation,
  demand submission and alerts. They are not silently inferred from another flag.
  This is an intentionally bounded transition, not a claim that every operation
  has its own admin checkbox. Super Admin has explicit full access.
- Only Super Admin can list/create/change employee accounts. Super Admin is excluded
  from the employee API list and cannot be changed through that API. Account changes
  write actor, old/new public values, reason and time in the same transaction. No
  plaintext passwords or hashes appear in these audit values. Null employee/name
  updates now clear fields; short password updates are rejected; inactive creation
  and APPROVER templates are supported. Editing preserves additional base roles.
- A partial unique index enforces at most one Super Admin. The explicit provisioning
  command uses private environment credentials and never auto-promotes an employee.
  The former shared-password/all-role-grants seeder is retired.
- Plant workflow scope comes from configured UUID bindings and current DB flags.
  Clearing a flag revokes access with an existing token. Workflow list queries filter
  permitted plants. Legacy `user_plants` rows are retained but do not override flags.
- Masters → Products offers manual creation and a read-only Excel preview. Operators
  choose the verified code source and units before saving a reviewed batch. Item ID
  and Part No. are retained separately; missing values are not fabricated. Reviewed
  product batches are atomic and write source-reference audit records.
- PRD import recognises the KNL multirow Month/revision layout. An explicit month
  selects its latest numeric revision unless a particular revision is requested.
  It preserves zero, rejects blank/invalid quantities and ambiguous product/plant
  references, checks units where supplied and uses reviewed master units otherwise.
  Valid imports populate existing staging, canonical planning/version/item models
  and workspace display rows together. Revision numbers reflect the source, not
  upload arrival order; duplicate revisions are rejected. Verified source rows cannot
  be overwritten/deleted through workspace edits.
- Requirements displays stored canonical calculation results for the latest revision
  of each period. It no longer invents percentage demand, consumable identities, MSL,
  stock totals or undated PO availability. Stock/shortage/MSL fields say Unavailable
  here; authoritative dated projection/report services remain their source.
- Calculation uses the existing domain engine and explicit norms. Missing norms
  become configuration-error rows. Zero production does not resurrect old demand.
  Confirmed/approved calculation evidence cannot be overwritten. Super Admin can
  approve a successfully calculated latest revision, with confirmations and audit
  evidence. This does not approve extra requests automatically or create a PO.
- Inventory offers a daily Excel statement preview using Item ID, Unit and Closing/
  Usable Quantity. It requires reported/export times and explicit exclusion checks.
  Unknown materials, unit mismatches and duplicate snapshots fail validation. The
  existing stock service imports the reviewed payload; replay does not duplicate
  balances, and balance reads use the latest dated snapshot rather than summing days.
- GRN workspace parsing requires a separate actual-received column. Order Qty,
  GRN/required Qty and Billed Qty cannot substitute. Unsupported positional fallback,
  invented zero-on-error quantities and replace-history mode are removed. The screen
  states that workspace rows do not fulfil a PO or post stock. Atomic authoritative
  GRN integration remains the existing `/grns/imports` contract, with explicit accepted
  and rejected quantities, source keys, PO-item references and stock evidence.

## Schema and API impact

New migrations, without modifying applied revisions:

1. `0020` after `ee17a6e77f73`: unique filtered index on Super Admin accounts. If the
   database already has several Super Admins, migration fails rather than deleting
   accounts or choosing an authority automatically; resolve that with owner review.
2. `0021`: nullable `products.item_id` and `products.part_number`. Existing products
   are preserved. Populate identifiers by a reviewed reconciliation; no blanket
   automatic backfill assumes that legacy product codes always mean Item ID.

New APIs:

- `POST /api/v1/masters/products/preview`: multipart file and sheet; preview only.
- `POST /api/v1/masters/products/reviewed`: reviewed products and source reference.
- `POST /api/v1/inventory/statement/preview`: multipart file, sheet, `as_of`,
  `generated_at`, `exclusions_confirmed`; returns the existing SourceImport payload.
- `POST /api/v1/requirements/planning-versions/{id}/approve`: Super Admin only.

Changed contracts:

- Employee creation returns 201 and supports `is_active` and optional audit reason.
  Employees can no longer manage users merely through an ADMIN base role.
- `/auth/me` returns effective permissions plus allowed plant UUIDs, computed on each
  request; JWTs remain identity tokens and do not freeze permission flags.
- PRD sheet import accepts optional `target_period` and `revision_label`. KNL revision
  columns require the explicit month. Old missing-header/default-value behaviour is
  intentionally rejected. The new verified adapter supports `.xlsx`; CSV PRD adapter
  work is not delivered here. Draft manual workspace rows remain separate from
  validated canonical planning and do not silently affect requirements.
- Source revisions use `R<number>`. Existing canonical records whose labels and stored
  version numbers disagree need review before further import. No approved historical
  records were rewritten automatically.
- Requirements workspace rows include planning period/revision and may use Calculated
  or Configuration required statuses and Unavailable quantity fields. Recalculate in
  React calls the canonical calculation endpoint, then refreshes stored results.
- The compatibility `/requirements/workspace/recalculate` endpoint refreshes stored
  results only; it does not fabricate calculations from manual workspace rows.

## Enable and test manually

1. Review/apply migrations on the intended environment using your private configured
   DATABASE_URL, from `C:\KN\backend`:

   ```powershell
   .\.venv\Scripts\python.exe -m alembic upgrade head
   ```

2. Set SUPER_ADMIN_USERNAME and SUPER_ADMIN_PASSWORD privately if provisioning is
   needed; no default credentials are supplied. Use the existing Super Admin identity
   if one exists. Provision explicitly after migrations:

   ```powershell
   .\.venv\Scripts\python.exe -m app.db.bootstrap_admin
   ```

   This does not reset a matching existing password. Explicit rotation requires
   `--rotate-password`; it must not be used casually against a shared account.

3. Restart backend and frontend, sign in and open Administration. Create a Planner
   with explicit planning-view/calculation flags and whichever reviewed master flags
   are necessary. Create other employees with only their intended grants. Check both
   allowed and denied actions. Ten flags do not configure every legacy operation.
4. Map PLANT_PERMISSION_IDS slots 1–5 to actual UUIDs returned by `/api/v1/plants`.
   Set only verified bindings; an unset slot grants nothing. Restart after settings
   changes. Assign/check employee flags and verify denial for other plants.
5. In Masters → Products, create one real reviewed product or preview `Prd. Order`.
   Choose Item ID/Part No. as the verified key, review all descriptions/units and save.
   Unknown code/unit data stays blocked rather than defaulting to PCS or Plant 1.
6. Configure plants, processes and routes with the existing production master APIs,
   then Product–Plant Routes and Product–Process–Consumable mappings. Those production
   master forms are not added to the Products page by this change. Add only reviewed
   norms and their explicit parameters/units/effective dates through Consumption Norms.
7. Planner → PRD upload: choose the production-order sheet, planning month and optional
   revision. Leave revision blank to choose the highest numeric revision for that
   month. Check validation failures; inspect older revisions through planning history.
8. Requirements: select the validated latest revision and calculate. Resolve every
   missing mapping/norm error. Review evidence, then Super Admin approves the revision.
   Additional demand retains its separate review and self-approval restrictions.
9. Inventory: after the source mapping is verified, an operator may enable
   INVENTORY_IMPORT_ENABLED. With explicit stock-import permission, select the stock
   worksheet, actual reported/export times and exclusion confirmation; preview then
   import. The sheet must represent the central store, not a mix of independent
   locations. Re-upload the identical file/times to check replay. Corrected same-time
   statements conflict and require the source-correction contract; never overwrite.
10. Use the existing dated projection/reorder/recommendation services and approval/PO
    screens with complete inputs. Initial outstanding POs need a verified register;
    unreceived POs cannot be reconstructed from GRNs. New POs remain commitments.
11. GRN Excel rows can be reviewed only when an actual-received field is supplied.
    Source-to-authoritative-GRN mapping still needs source line keys, inspection/
    acceptance meaning, PO-item mapping and correction handling. Never turn an
    unverified workspace row into inventory. For ordered 200, physical 200, rejected
    20 and no other exclusions: accepted 180 and pending 20; billed 200 does not alter
    stock. The owner's actual physical receipt example is not yet supplied.

## Real validation results

- Backend isolated tests: 40 passed, five existing deprecation warnings.
- Frontend tests: 48 passed, zero failures across eight test files.
- TypeScript build: passed. Vite production build: passed.
- `alembic heads`: one head, `0021`.
- PostgreSQL offline SQL from `ee17a6e77f73` through head: generated successfully.
- `git diff --check`: passed (line-ending notices only).
- Tests used isolated SQLite, synthetic workbooks/identities and mocked frontend APIs.
  No actual Supabase migration, PostgreSQL locking/concurrency run, real-role UAT,
  disaster recovery or KNL numeric golden acceptance was performed.

## Remaining production integration

The selected formula map's known errors/ambiguous MSL definitions, real parameter
approvals, actual-receipt export field and source-line mapping, opening outstanding
PO register, corrected/cancelled source import convention, plant UUID bindings and
initial master/norm data still need verified values. Weekly scheduling and precise
need-date/lead-time-calendar behaviour are not invented from monthly PRD quantities.
Automatic recalculation/alert scheduling and complete workbook output-layout parity
are not delivered by this foundation. Existing report/alert policy concerns from
the earlier review still need follow-through; do not rely on placeholder alerts.

The original workbook can legitimately fail validation for blank latest-revision
quantities or unverified identities/units. Do not relabel those as zero to make an
import appear successful. The supplied formula map was used as design evidence,
not copied wholesale as approved executable business logic.
