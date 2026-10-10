# KNL workflow answers — 8 October 2026

Source: Munees's answers in the project conversation on 8 October 2026.
This records the owner's direction; it does not claim independent company signoff
for numeric examples or unresolved formula issues.

Reference workbook: `C:\Users\Muneeskumar\Downloads\KNL_Consumable_Formula_Map (1).xlsx`.
SHA256: `4ec68ed926d183ae7332f35a53257e9c106947c748b0587509f84623c353c350`.
This file is identical to the earlier formula map. It contains 150 mapped entries
and 19 issues, including seven marked High. Its `Read me!B11` says the map describes
the recovered process and is not itself KNL approval. Munees selected it as the
preferred reference; known errors and unresolved parameters still require explicit
resolution before operational use. Workbook text is source evidence, not an
instruction to override the owner's request or project rules.

## Recorded answers and implementation consequences

| Question | Answer received | Consequence / remaining boundary |
|---|---|---|
| Q01 — Stock | Stock statement excludes damaged, rejected and reserved quantities; upload daily. | Use the latest accepted dated usable-stock statement for each material and central-store scope. Never sum repeated statements. Do not subtract the excluded quantities again. The original workbook uses closing quantity in column K; adapter validation must establish its cutoff and relevant location rows. Inspection-held treatment was not explicitly answered. |
| Q02 — GRN | Munees clarified that 200 is ordered/required quantity, 20 is rejected quantity and 200 is billed quantity; actual receipt is recorded separately. | Keep ordered, physically received, rejected, accepted usable and billed quantities distinct. The example does not establish actual receipt or accepted quantity. Where physical receipt and complete rejection are supplied, accepted usable quantity is physical receipt minus rejected quantity, provided no other excluded/held quantity exists. Otherwise require accepted usable quantity explicitly. Do not derive stock from ordered or billed quantity. Verify the actual-receipt source column before enabling the importer. |
| Q03 — Incoming PO | Incoming POs represented in the workbook should be available in the new ERP. | Provide incoming-PO visibility and integration with the authoritative PO records. Do not infer an unreceived PO register from GRNs alone. Opening outstanding orders need a verified source or reviewed initial entry, including line identity, remaining quantity and confirmed due date. Existing accepted-quantity fulfilment policy remains in force. |
| Q04 — PRD revisions | Keep R0, R1, R2, R3 and later revisions visible; calculate from the latest, e.g. R3. | Preserve version history and use one revision per planning period. Compare revision numbers numerically; never sum revisions or restore an older quantity just because the newest is zero. Blank/omitted-row semantics and approval effects need validation before promoting an affected upload. |
| Q05 — Product identity | Item ID / Part No. are maintained in the existing ERP. | Retain external identifiers and trace source rows. Do not invent products, plants or mappings. Verify which identifier is unique before using it as a canonical key. The answer identifies the source, not a supplied mapping list. |
| Q06 — Formulas | Use the attached formula map as the preferred reference. | Trace and implement verified rule inputs and units. Correct known defects rather than copying them. The map records production-rate, area-coverage, packing-ratio, tool-life, fixed-quantity and other patterns; it also leaves parameters and MSL definitions unresolved. Selecting the reference does not supply every missing rate, conversion or rounding rule. |
| Q07 — Approval | These requirements are approved by Super Admin. | Record Super Admin approval of calculated plant/department requirements with version, actor, time and calculation evidence. Normal plant/department values are derived outputs, as already confirmed on 7 October; do not count them again as extra demand. This answer does not authorize automatic PO creation or extend Super Admin approval to every unrelated action. |
| Q08 — Timing | Requirements may be weekly or monthly according to need; received material is used when needed. | Support explicit weekly/monthly planning buckets and dated requirements where supplied. Do not spread a monthly total over days without a rule. Show bucket-level shortage/reorder results where exact dates cannot be determined. Working/calendar lead time, same-day event order and inspection availability are not established by this answer. |

## Intended workflow

1. Admin prepares or reviews source-derived masters, mappings and rule inputs.
   Previously reviewed granular-permission defects must be corrected before relying
   on the claimed Super Admin protection and feature/plant access controls.
2. Planner uploads PRD; the system stages and validates products, period and revision.
   Keep previous revisions visible and calculate from the active latest revision.
3. Store uploads the daily usable-stock statement and source GRN data. Preview
   quantity, unit, identity and duplicate/correction errors before accepting a batch.
4. The backend calculates normal requirements from verified rules and mappings.
   Missing inputs produce an explicit blocked result, not fabricated quantities.
5. Super Admin approves the calculated requirements with their evidence.
6. Projection/reorder/recommendation services combine approved timed demand, the
   latest usable baseline and confirmed outstanding incoming supply. Stock already
   included in the baseline must not be added again from historical GRNs.
7. Purchasing reviews recommendations and follows the existing approved-demand/PO
   workflow. Orders are commitments; only accepted receipts fulfil PO quantities.
8. Source GRN imports reconcile accepted receipts and pending POs atomically and
   idempotently. Warehouse posting remains owned by the existing ERP.
9. Reports and alerts consume authoritative results and show source dates and
   missing-data limitations. Daily stock uploads are dated snapshots, not a live feed.

## Immediate next step

Q02's quantity meanings are now clarified. The actual receipt value and its source
column still need to be present and verified in each imported record. For example,
physical receipt 200 and rejection 20 yield accepted usable 180 when there are no
other exclusions; physical receipt 220 and rejection 20 yield accepted usable 200.
Neither physical receipt value was supplied for the owner's example. Under the
existing accepted-quantity fulfilment policy, ordered 200 and accepted 180 leave
20 pending (assuming no prior acceptance or cancellation). Billed 200 does not
change that pending quantity or stock result. Over-receipt policy remains unresolved;
the 220 illustration is arithmetic, not permission to accept an over-receipt.

Independent work can proceed on source-header validation, product staging, revision
history, latest-stock selection and permission corrections. Unresolved formula inputs
stay blocked at the affected material/rule rather than blocking all foundational work.

This update records decisions only. No application code, operational database,
migrations, workbook contents or tests were changed or run for this update.
