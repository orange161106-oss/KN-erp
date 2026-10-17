"""Explicit additive migration runner for tool-life columns."""
import os
import sys

backend_path = os.path.abspath(r"backend")
sys.path.insert(0, backend_path)

from app.core.config import load_settings
from app.db.session import create_db_engine
from sqlalchemy import inspect, text

settings = load_settings()
engine = create_db_engine(settings)

with engine.begin() as conn:
    print("Executing additive ALTER TABLE statements...")
    conn.execute(text("ALTER TABLE consumables ADD COLUMN IF NOT EXISTS output_per_unit NUMERIC(14, 4);"))
    conn.execute(text("ALTER TABLE consumables ADD COLUMN IF NOT EXISTS rule_type VARCHAR(32) DEFAULT 'TOOL_LIFE';"))
    conn.execute(text("ALTER TABLE consumables ADD COLUMN IF NOT EXISTS purchasing_unit VARCHAR(32);"))
    conn.execute(text("ALTER TABLE consumption_norms ADD COLUMN IF NOT EXISTS output_per_unit NUMERIC(14, 4);"))
    print("Columns added successfully.")

inspector = inspect(engine)
c_cols = [c["name"] for c in inspector.get_columns("consumables")]
n_cols = [c["name"] for c in inspector.get_columns("consumption_norms")]
print("Consumables columns:", c_cols)
print("Consumption_norms columns:", n_cols)
assert "output_per_unit" in c_cols, "output_per_unit missing from consumables"
assert "rule_type" in c_cols, "rule_type missing from consumables"
assert "purchasing_unit" in c_cols, "purchasing_unit missing from consumables"
assert "output_per_unit" in n_cols, "output_per_unit missing from consumption_norms"
print("All verification checks PASSED!")

