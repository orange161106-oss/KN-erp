"""Fast bulk populate output_per_unit, rule_type, and purchasing_unit."""
import os
import sys
from decimal import Decimal
import openpyxl

backend_path = os.path.abspath(r"backend")
sys.path.insert(0, backend_path)

from app.core.config import load_settings
from app.db.session import create_db_engine
from sqlalchemy import text

plan_path = r"C:\Users\YATHISH\.gemini\antigravity\brain\f9e7e4a4-f865-4ca3-b0ab-9aea1399a503\scratch\oct_plan_copy.xlsx"
wb = openpyxl.load_workbook(plan_path, read_only=True, data_only=True)
ws = wb["Plan"]
items_data = []
for r_idx, row in enumerate(ws.iter_rows(min_row=4, max_row=1000, values_only=True), start=4):
    if len(row) > 3 and row[2] and str(row[2]).strip():
        cid = str(row[2]).strip().upper()
        supp_id = str(row[0]).strip() if row[0] else None
        supp_name = str(row[1]).strip() if row[1] else None
        cat = str(row[3]).strip() if row[3] else None
        desc = str(row[6]).strip() if row[6] else None
        out_unit = row[13]
        pur_unit = str(row[27]).strip() if len(row) > 27 and row[27] else None
        
        tool_life = None
        if out_unit is not None:
            try:
                tool_life = float(Decimal(str(out_unit)))
            except Exception:
                pass
        
        rule_type = "TOOL_LIFE" if (tool_life and tool_life > 1) else "PRODUCTION_RATE"
        if "powder" in (desc or "").lower():
            rule_type = "AREA_COVERAGE"
            
        items_data.append({
            "item_id": cid,
            "supp_name": supp_name,
            "category": cat,
            "output_per_unit": tool_life if tool_life is not None else 1.0,
            "rule_type": rule_type,
            "purchasing_unit": pur_unit,
        })
wb.close()
print(f"Loaded {len(items_data)} items from Plan sheet.")

settings = load_settings()
engine = create_db_engine(settings)

with engine.begin() as conn:
    # 1. Bulk update consumables using executemany
    update_c_sql = text("""
        UPDATE consumables
        SET output_per_unit = :output_per_unit,
            rule_type = :rule_type,
            purchasing_unit = COALESCE(:purchasing_unit, purchasing_unit),
            category = COALESCE(:category, category),
            supplier_name = COALESCE(supplier_name, :supp_name)
        WHERE item_id = :item_id
    """)
    conn.execute(update_c_sql, items_data)
    print("Consumables bulk-updated successfully.")

    # 2. Fast single SQL statement to sync consumption_norms from consumables
    update_norm_sql = text("""
        UPDATE consumption_norms cn
        SET output_per_unit = c.output_per_unit,
            rule_type = COALESCE(c.rule_type, 'TOOL_LIFE')
        FROM consumables c
        WHERE cn.consumable_id = c.id;
    """)
    res = conn.execute(update_norm_sql)
    print(f"Synced {res.rowcount} consumption_norms from consumables.")

    # 3. Verify target items
    verify_sql = text("""
        SELECT item_id, output_per_unit, rule_type, purchasing_unit, category, supplier_name
        FROM consumables
        WHERE item_id IN ('AAC100001QC', 'AAC100002QC', 'AAC100003QC', 'BAC000020QC', 'NBQ000031QC', 'ABA100001QC')
    """)
    rows = conn.execute(verify_sql).fetchall()
    print("--- VERIFICATION ---")
    for r in rows:
        print(dict(r._mapping))

print("DONE!")
