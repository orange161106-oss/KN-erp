"""Idempotent migration to correct consumable rule_type values per KNL-Formula.xlsx."""
import os
import sys

backend_path = os.path.abspath(r"backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from app.core.config import load_settings
from app.db.session import create_db_engine
from sqlalchemy import text


def fix_master_rules():
    settings = load_settings()
    engine = create_db_engine(settings)

    with engine.begin() as conn:
        print("1. Updating table default for consumables.rule_type to 'DIRECT'...")
        # Check dialect
        dialect = engine.dialect.name
        if dialect == "postgresql":
            conn.execute(text("ALTER TABLE consumables ALTER COLUMN rule_type SET DEFAULT 'DIRECT';"))

        print("2. Correcting 96 Stationery and Housekeeping items to 'DIRECT'...")
        res_stat = conn.execute(text("""
            UPDATE consumables
            SET rule_type = 'DIRECT'
            WHERE (
                item_id LIKE 'PEQ%' OR 
                item_id LIKE 'PDQ%' OR 
                item_id LIKE 'FDQ%' OR
                category = 'Stationary' OR
                category = 'Housekeeping items'
            ) AND rule_type != 'DIRECT';
        """))
        print(f"   Updated {res_stat.rowcount} stationery/housekeeping consumables to DIRECT.")

        print("3. Correcting Welding Wire, PPE, and Spray consumables to 'DIRECT'...")
        res_direct = conn.execute(text("""
            UPDATE consumables
            SET rule_type = 'DIRECT'
            WHERE (
                item_id LIKE 'ABB%' OR
                item_id LIKE 'ABM%' OR
                item_id LIKE 'ADQ%' OR
                item_id LIKE 'GAQ%' OR
                type_of_material = 'Welding' OR
                type_of_material = 'Safety' OR
                type_of_material = 'PPE'
            ) AND rule_type != 'DIRECT';
        """))
        print(f"   Updated {res_direct.rowcount} welding/PPE/spray consumables to DIRECT.")

        print("4. Ensuring genuine Cutting Tools retain 'TOOL_LIFE'...")
        res_tools = conn.execute(text("""
            UPDATE consumables
            SET rule_type = 'TOOL_LIFE'
            WHERE (
                type_of_material = 'Cutting Tools' OR
                item_id LIKE 'AAC%' OR
                item_id LIKE 'AAG%' OR
                item_id LIKE 'AAH%' OR
                item_id LIKE 'BAC%' OR
                item_id LIKE 'BAA%' OR
                item_id LIKE 'BAB%'
            ) AND item_id NOT LIKE 'PEQ%' AND item_id NOT LIKE 'ABB%'
              AND rule_type != 'TOOL_LIFE';
        """))
        print(f"   Updated/preserved {res_tools.rowcount} machining consumables as TOOL_LIFE.")

        print("5. Syncing consumption_norms rule_type with consumables...")
        if dialect == "postgresql":
            conn.execute(text("""
                UPDATE consumption_norms cn
                SET rule_type = c.rule_type
                FROM consumables c
                WHERE cn.consumable_id = c.id
                  AND cn.rule_type != c.rule_type;
            """))

        # Verify target test items
        verify_sql = text("""
            SELECT item_id, name, category, type_of_material, rule_type, output_per_unit
            FROM consumables
            WHERE item_id IN ('AAC100001QC', 'ABB100011QC', 'PEQ000075QC', 'AFE000001QC', 'NBQ000032QC', 'GAQ000078QC', 'BAA110116QC', 'AAC100017QC')
            ORDER BY item_id;
        """)
        rows = conn.execute(verify_sql).fetchall()
        print("\n--- TARGET ITEMS VERIFICATION ---")
        for r in rows:
            print(dict(r._mapping))

    print("\nMaster rules correction completed successfully.")


if __name__ == "__main__":
    fix_master_rules()
