# AI Build Rules

All AI coding agents must follow this file.

## Before coding
AI must receive:
1. task
2. owner/module
3. relevant docs
4. existing code context
5. acceptance criteria

## AI must never
- invent manufacturing formulas
- invent MSL/MOQ/lead time/pack size
- invent approval authority
- invent fields just to make UI work
- silently change architecture
- modify another teammate's domain without explicit scope
- put authoritative logic in React
- put business formulas in FastAPI routes
- bypass layer boundaries
- use float for precise money/quantities
- delete audit/history
- modify applied migrations
- duplicate existing domain models
- add Celery/Redis/microservices without approved need
- add AI/ML business logic
- hard-code company data that belongs in masters
- replace an approved rule with an assumed "better" rule

## AI must
- inspect existing code before creating new structures
- follow naming conventions
- reuse domain concepts
- add/update tests
- validate errors and edge cases
- preserve auditability
- make calculations explainable
- mark unknowns `TBD`
- keep changes within task scope
- report files changed
- report migration/API impact
- report assumptions and cross-team effects

## Build order
1. Read docs
2. Confirm owner/module
3. Define acceptance criteria
4. Define/update domain model
5. Define DB changes
6. Define API contract
7. Implement domain logic
8. Implement service/repository
9. Implement API
10. Implement frontend
11. Add tests
12. Run tests
13. Update docs

## Calculation rule requirements
Every rule needs:
- named type
- inputs
- output
- units
- rounding
- validation
- deterministic tests
- source/approval reference where applicable

AI-generated code remains a draft until tests pass and the owner reviews it.
