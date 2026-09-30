# Testing, Security and Definition of Done

## Testing
Unit-test pure domain calculations.

Integration/API-test:
- repositories
- DB transactions
- API validation
- permissions
- stock changes
- PO/GRN effects

Create company-approved golden test cases with:
- input
- expected result
- unit
- rounding
- source/approval

Test edge cases:
- zero/negative quantities
- missing norm
- zero denominator
- stock at/below MSL
- pending PO > requirement
- MOQ > raw quantity
- order-multiple rounding
- duplicate import rows
- concurrent stock/GRN updates
- unauthorized approval

## Security
- backend is authorization authority
- use permission-based operations
- plant scope enforced server-side
- secrets only in environment/secret store
- validate Excel type/size/structure
- staging data cannot affect planning before validation

## Audit
Log critical changes to:
- masters
- norms
- MSL/MOQ/lead time
- requirement adjustments
- approvals
- stock adjustments
- purchase overrides
- PO/GRN
- roles/permissions

Audit minimum:
actor, action, entity, old/new values where applicable, reason, timestamp.

## Definition of Done
A feature is done only when:
- acceptance criteria pass
- business rule is approved
- API validation exists
- authorization exists
- domain/service/repository separation is maintained
- migration is valid
- audit behavior exists if required
- UI handles loading/empty/errors
- tests pass
- docs match behavior
- no cross-team contract is silently broken
