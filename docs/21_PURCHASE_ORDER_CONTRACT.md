# M5.3 purchase orders

Owner: Munees. Reviewer: Keerthi. Company: KNL.
Branch: `feature/munees/m5.3-purchase-orders`.

## Commitment and approval boundary

A PO is a purchase commitment, never a receipt or consumption transaction. Creating,
issuing or cancelling a draft does not write stock snapshots, movements or projected
incoming supply. Confirmed incoming stays subject to the M4.2 source/reconciliation
contract, so a PO must not be counted a second time through an automatic shortcut.

M5.2 stores approval quantities but does not retain the original M5.1 calculation
evidence. Munees explicitly selected: **use traced submissions; resubmit older
approvals**. Therefore a legacy APPROVED/MODIFIED row alone cannot create a PO.
Do not attach a new calculation to an old approval retrospectively.

The new traced submission endpoint runs M5.1 on the server, requires a complete
positive recommendation, atomically saves its full response and a new PENDING
M5.2 queue row, and audits submission. Existing M5.2 review handles that row normally,
including independent review, quantity override/reason and rejection. It does not
grant new approval authority or alter the existing approval actions.

PO creation accepts only APPROVED or MODIFIED rows with a positive approved quantity,
reviewer/time, independent reviewer, active masters/mapping and eligible planning
version. Original material/supplier/unit/version/rule/raw/recommended quantities
must match the immutable submitted evidence. Modified approvals require their
recorded reason. Draft issuance rechecks eligibility and the exact approval snapshot.
Superseded/draft planning versions and altered approvals are rejected.

## Storage and traceability

Migration `0015_purchase_orders` follows `0014_purchase_approval` and creates:

- `purchase_demand_evidence`: one immutable server-generated M5.1 report per queue
  row, unique submission key/hash, submitter and time. The report retains the
  recommendation inputs, source projection, requirement fingerprint, stock snapshot,
  incoming, target, supplier constraints and calculation steps.
- `purchase_orders`: unique technical PO identifier, unique creation key/hash,
  supplier identity/name/code snapshot, PO date, status, reason and actor/time fields.
- `purchase_order_items`: approval/evidence/material/unit/planning-version references,
  approved-source snapshot/hash, material/unit snapshot, exact quantity, expected
  usable delivery timestamp, optional pricing evidence and Decimal line value.

PO numbering currently uses `PO-` plus the full generated UUID, without a guessed
financial-year or company numbering sequence. KNL's external/legal numbering pattern
remains a separate integration decision. User-provided duplicate PO numbers are not
accepted. Quantities are NUMERIC(18,4); line values use NUMERIC(38,8). Existing M5.2
NUMERIC(14,4) submission limits are checked explicitly rather than silently truncated.

PostgreSQL rejects UPDATE/DELETE of demand evidence and PO items. PO headers cannot
be deleted or have terms overwritten; only a DRAFT-to-ISSUED/CANCELLED transition
with actor/time is permitted. Application audits commit in the same transaction as
each submission, creation or transition. Correct draft terms by cancelling and
creating a new draft; history remains intact. No applied migration is edited.

## Allocation, retries and state

Draft quantities reserve approved demand. Available allocation equals approved
quantity less quantities in all non-cancelled POs, including drafts. Approval rows
are locked in deterministic ID order. Separate SERIALIZABLE transactions ensure
that concurrent source/allocation changes cannot produce two successful excess
allocations. Serialization/deadlock conflicts return retryable 409; retry unchanged.

Submission/creation keys are unique. Identical retries return 200 and replayed=true;
different content under the same key returns 409. New records return 201. Issuing
an already-issued PO or cancelling an already-cancelled draft is also an idempotent
read of the result, without another audit record. The frontend retains the same
creation key across retries of an unchanged form.

Partial allocations must still satisfy the saved M5.1 MOQ, pack, order-multiple
and maximum-order terms. The M5.1 engine is reused rather than duplicating rounding
rules. A whole MODIFIED approved quantity is an explicit reviewed override with
its reason; that exception is not extended silently to arbitrary splits. No new
target-stock calculation or guessed stock value is introduced during PO creation.

Implemented states:

- DRAFT: approved demand allocated, no purchasing commitment issued.
- ISSUED: commitment recorded by a user with explicit issue permission. Issuing is
  internal recording, not emailing or otherwise transmitting a PO to a supplier.
- CANCELLED: a cancelled draft, with history retained and allocation released.

PARTIALLY_RECEIVED/CLOSED and issued cancellation require a linked fulfilment and
reversal contract. They are deliberately not manually selectable states in this
milestone. Issued quantities/terms cannot be silently edited or cancelled while
receipt status is unknown. No procurement authority is inferred from role names.

## Pending quantity and future receipt integration

Proposed invariant:
`pending = ordered - cancelled - source-approved fulfilled quantity`.
Exact arithmetic rejects overfulfilment/overcancellation. Unknown fulfilled quantity
produces unknown pending, not zero and not the full ordered amount.

This repository has no approved PO-linked receipt adapter yet. Consequently:

- Drafts/cancelled drafts report pending commitment 0 (NOT_COMMITTED/CANCELLED_DRAFT).
- Issued items report pending_quantity=null with FULFILMENT_NOT_CONNECTED.
- The UI explains the missing connection and never fabricates received quantities.

The pure pending service is tested for zero, partial and complete fulfilment, but
operational fulfilment is not claimed. KNL must confirm whether accepted quantity
alone fulfils an order and how rejection/replacement/cancellation is reconciled.
A future linked GRN/source adapter must supply that cumulative auditable evidence
before receipt states and issued cancellation are enabled. It must also protect
against duplicate source receipts. This is a material operational limitation.

## Pricing

Pricing is optional. Unpriced line values and any incomplete PO total are null,
never zero. A user needs `purchase.orders.price` as well as create permission to
enter an approved unit rate, three-letter currency, decimal places (0–4), rounding
HALF_UP/HALF_EVEN/DOWN and pricing approval reference. No currency/rate/rounding default
is invented. All priced lines share one currency/rounding policy. Values are
calculated on the server using Decimal, stored exactly, and serialized as strings.

`line value = ordered quantity × unit rate`, rounded once using the supplied
currency precision/rule. Total is the sum of priced line values only when all lines
are priced. The frontend never multiplies binary floating-point quantities/rates.
Tax, freight, discounts and foreign-exchange conversion are not calculated. A quote
reference is recorded evidence, not independent electronic approval verification.

## APIs and permissions

| API | Explicit grants |
| --- | --- |
| POST `/api/v1/purchase-orders/demand` | `purchase.demand.submit` and `inventory.projection.read` |
| GET `/api/v1/purchase-orders/eligible` | `purchase.orders.read` |
| GET `/api/v1/purchase-orders` | `purchase.orders.read` |
| GET `/api/v1/purchase-orders/{id}` | `purchase.orders.read` |
| POST `/api/v1/purchase-orders` | `purchase.orders.create`; also price when terms supplied |
| POST `/api/v1/purchase-orders/{id}/issue` | `purchase.orders.issue` |
| POST `/api/v1/purchase-orders/{id}/cancel` | `purchase.orders.cancel` |

Migration seeds the six new permission codes, with no users, role grants or company
data. M5.2's `purchasing:approve` continues to control review. List/eligible endpoints
are paginated (25 default, 100 maximum); each returns a page of typed records.
Creation has 1–100 distinct approval items for one supplier. Requests reject extra
fields, naive timestamps, nonpositive/inexact quantities and mixed pricing policies.
Creation and every transition require a reason. Backend checks precede mutation;
React visibility is not authorization. Database errors are sanitized.

## Frontend and setup

`/purchase-orders` is available through a permission-controlled sidebar link.
It lists POs, displays detail and approval/calculation history, selects eligible
approved demand, collects exact quantity strings/delivery timestamps, optionally
collects approved pricing and saves drafts. Issue/cancel controls require their
explicit permissions and reason. Legacy/unavailable approvals explain their
limitation and cannot be selected. Loading, empty, error, retry and unpriced/pending
unknown states are visible. Local datetime input converts to UTC before submission.

Traced submission is an integration API accepting the existing M5.1 PurchaseRequest
inside `{submission_key, reason, recommendation}`. It creates a PENDING entry visible
in the existing Purchase Approvals screen. M5.1 source-data configuration and a new
recommendation-entry UI are outside this PO screen; do not submit client-calculated
quantities through the legacy endpoint expecting them to become traceable.

Run `alembic upgrade head` and `alembic check` using the existing configured environment.
No new environment variables are introduced. Give approved operators the exact grants
needed for their duties; do not grant them automatically based on a role label.

Migration validation also exposed redundant `index=True` declarations on M5.2's
supplier/material columns. Those declarations were removed while keeping its explicit
named indexes and applied migration unchanged. No approval business rule changed.

## Acceptance and remaining decisions

Tests cover traced submission/review, rejected/unapproved/legacy denial, quantities
and split constraints, retry keys, concurrent allocation, immutable database history,
audit rollback, price precision, pure pending quantities, stock unchanged, source
changes and server permissions. Frontend tests cover grants, empty/loading/errors,
legacy limitation, exact string submission, retry key reuse, issue reason and unknown
pending. PostgreSQL migration upgrade/downgrade/metadata checks are required.

KNL decisions still needed: linked accepted/rejected fulfilment, issued cancellation
and amendment policy, external PO numbering and external price approval verification.
All test business values are synthetic. The implemented commitment workflow can be
reviewed independently, but full receiving/pending reporting cannot be signed off
until the fulfilment integration is supplied.
