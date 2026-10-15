"""Read-only database latency/schema diagnostic; never display credentials/data."""
import json
from time import perf_counter

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import app.models  # Register the shared metadata without starting the server.
from app.core.config import load_settings
from app.db.base import Base
from app.db.reliability import database_failure
from app.db.session import create_db_engine


def run() -> dict:
    settings = load_settings()
    engine = create_db_engine(settings)
    report = {"pool_connection_limit_per_worker": settings.db_pool_size + settings.db_max_overflow}
    try:
        timings = []
        for _ in range(3):
            start = perf_counter()
            with engine.connect() as connection:
                connection.execute(text("SELECT 1")).scalar_one()
            timings.append(round((perf_counter() - start) * 1000))
        report["connection_round_trip_ms"] = timings
        # One metadata query, rather than querying each table over a remote link.
        with engine.connect() as connection:
            columns = connection.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = current_schema()"
            )).all()
        available = {}
        for table, column in columns:
            available.setdefault(table, set()).add(column)
        missing = {
            table.name: sorted({column.name for column in table.columns} - available.get(table.name, set()))
            for table in Base.metadata.sorted_tables
        }
        report["missing_schema_columns"] = {table: names for table, names in missing.items() if names}
        report["status"] = "schema_mismatch" if report["missing_schema_columns"] else "ok"
    except SQLAlchemyError as error:
        category, state = database_failure(error)
        report.update(status="unavailable", category=category, sqlstate=state)
    finally:
        engine.dispose()
    return report


def main() -> int:
    report = run()
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
