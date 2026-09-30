# KN Consumable ERP — Documentation Index

This `docs/` folder is the single source of truth for the KN Consumable ERP.

If code and documentation disagree, stop and resolve the conflict before continuing.

## Mandatory AI read order
1. `01_PROJECT_SCOPE.md`
2. `02_PROJECT_RULES.md`
3. `03_TECH_STACK.md`
4. `04_SYSTEM_ARCHITECTURE.md`
5. `05_DOMAIN_BUSINESS_RULES.md`
6. `06_DATABASE_AND_API_RULES.md`
7. `07_AI_BUILD_RULES.md`
8. `08_TEAM_OWNERSHIP.md`
9. `09_GIT_WORKFLOW.md`
10. `10_TESTING_SECURITY_DOD.md`
11. `11_ROADMAP.md`
12. `12_AI_TASK_TEMPLATE.md`
13. relevant file in `team/`
14. relevant ADR in `adr/`

## Finalized stack
- React + TypeScript + Vite
- Tailwind CSS
- Python + FastAPI + Pydantic
- PostgreSQL
- SQLAlchemy
- Alembic
- openpyxl
- pandas only where genuinely useful
- Celery + Redis only when background/scheduled jobs become necessary

## Golden rule
AI must never invent a manufacturing/business rule. Unknown rules must be marked `TBD`.
