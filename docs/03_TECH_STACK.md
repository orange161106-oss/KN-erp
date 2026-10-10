# Finalized Technology Stack

## Frontend
- React
- TypeScript
- Vite
- Tailwind CSS
- Recharts where required

## Backend
- Python
- FastAPI
- Pydantic

## Database
- PostgreSQL
- SQLAlchemy
- Alembic

## Excel/Data
- openpyxl for `.xlsx`
- pandas only for useful tabular transformation/analysis

## Background jobs
Do not add prematurely.

When genuinely required:
- Celery
- Redis

Use for scheduled MSL checks, shortage checks, PO-delay checks, large imports, and scheduled reports.

## Operations
- Git/GitHub
- Docker
- environment variables/secrets
- structured logging
- automated tests
- CI/CD when deployment begins
- automated PostgreSQL backups in production

## Prohibited architecture shortcuts
- Firebase/MongoDB as main ERP database
- Excel as permanent calculation engine
- authoritative business logic in React
- business formulas inside FastAPI route functions
- AI/ML/LLM as Phase-1 business engine
