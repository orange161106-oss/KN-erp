# KNL inventory/purchase example — capture and approval

Copy one sheet per real consumable/supplier/planning version. Gather existing ERP
stock/PO/GRN reports and the approved requirement workbook. Use the consumable's
stock unit throughout. If units differ, record approved conversion evidence before
normalizing the quantities. Do not fill missing values from development examples.

## Identity and source evidence

| Field | KNL-confirmed answer |
|---|---|
| Case ID; material code/name; stock unit | TBD |
| Selected supplier code/name | TBD |
| Planning month/version; covered plants | TBD |
| Input ERP export/workbook/sheet/cell references | TBD |
| Independent expected calculation/workbook references | TBD |
| Case-pack/source SHA-256 | TBD |
| Named KNL approver and approval date/time | TBD |
| Rule/policy/constraint references and effective interval | TBD |

## Stock and requirement

| Field | KNL-confirmed answer |
|---|---|
| Central usable stock and exact snapshot timestamp/timezone | TBD |
| Damaged/rejected/inspection-pending excluded? | TBD — confirmation required |
| Reserved stock already excluded? | TBD — confirmation required |
| Stock export/snapshot IDs and export generation time | TBD |
| Final approved requirement per plant | TBD |
| Already fulfilled requirement per plant at snapshot | TBD |
| Reserved demand already excluded from usable stock per plant | TBD |
| Remaining dated demand: unique source ID, quantity and exact time per event | TBD |
| Reconciliation evidence and coverage end time | TBD |

Final requirement = fulfilled + reserved already excluded + dated remaining demand.
Monthly-only timing is unknown; do not divide it into daily/weekly amounts.

## Incoming PO schedules

Copy a row per unique schedule, not merely per shared PO header. Explicitly confirm
`NONE` when there is no incoming supply.

| PO/item/schedule ID | Confirmed status | Scheduled qty | Already accepted/received at snapshot | Cancelled qty | Usable-availability timestamp | Evidence |
|---|---|---|---|---|---|---|
| TBD | TBD | TBD | TBD | TBD | TBD | TBD |

Rejected material stays outside usable stock. Pending replacement is not a second
confirmed schedule unless supplied explicitly. Outstanding = scheduled less already
accepted/received and cancelled. Ordered PO quantity is not received stock.

## MSL, lead time and supplier terms

| Field | KNL-confirmed answer |
|---|---|
| MSL value/history, effective timestamps and approval | TBD |
| Policy: below MSL or at-or-below MSL? | TBD |
| Receipt allowed at crossing or strictly before it? | TBD |
| Reorder evaluation time and exclusive projection horizon | TBD |
| Lead-time days, start/end events, effective interval | TBD |
| Elapsed 24-hour days or working days? | TBD |
| Working-day calendar: coverage and explicit working dates | TBD if applicable |
| Order initiation and material-usable receipt timestamps | TBD |
| Target at receipt and approval/effective interval | TBD |
| MOQ: applicable value / explicitly not applicable / unknown | TBD |
| Pack: applicable value / explicitly not applicable / unknown | TBD |
| Multiple: applicable value / explicitly not applicable / unknown | TBD |
| Maximum order/stock: applicability and values | TBD |
| Other constraints: confirmed none or specified restrictions | TBD |

Unknown is not zero or not applicable. Confirm KNL accepts the documented simultaneous
pack/multiple convention; if it differs, record approved policy changes rather than
altering expectations to match development output.

## Independently expected answers

| Expected result | KNL-confirmed calculation |
|---|---|
| Current usable stock and selected snapshot | TBD |
| Projected stock at each event and horizon | TBD |
| Projected stock immediately before usable purchase receipt | TBD |
| MSL condition and first future breach/no breach | TBD |
| Reorder required now: yes/no/unknown | TBD |
| MSL-policy crossing date/time, including equality policy | TBD |
| Latest safe order point and inclusivity | TBD |
| Incoming included before receipt and excluded amounts | TBD |
| Raw purchase quantity | TBD |
| After MOQ; common increment; rounded candidate | TBD |
| Recommended quantity or incomplete/conflict reason | TBD |
| Stock after purchase receipt | TBD |
| Quantity precision, rounding rule and maximum conflicts | TBD |

Use KNL's independent reviewed calculation. Preserve unknown/null answers when not
determinable; require the application to explain the limitation.

## Investigation and sign-off

| Case/field | Expected | Actual | Cause/impact | Correction/approval | Retest | Owner/reviewer sign-off |
|---|---|---|---|---|---|---|
| TBD | TBD | TBD | Not compared yet | TBD | TBD | TBD |

KNL input/expected-answer approval: TBD. Reviewer comparison/closed-difference
approval: TBD. This blank sheet does not approve an example.
