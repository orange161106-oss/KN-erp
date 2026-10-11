import io
import openpyxl
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.main import app
from app.models.auth import User
from app.security.passwords import PasswordService
from app.models.inventory_masters import Unit, Consumable
from app.models.masters import Product
from app.models.production import Process
from app.services import product_master_service as service


from sqlalchemy import event


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def configure(connection, record):
        connection.create_function("btrim", 1, lambda val: val.strip() if val else "")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def make_excel_workbook(rows: list[list]):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_phase4_product_master_service_and_header_hunter(db):
    user = User(username="test_admin", password_hash="secret", is_super_admin=True)
    db.add(user)
    db.commit()

    # 1. Test single consumable upsert with UOM auto-provisioning
    cons_data = service.ConsumableSingleCreate(
        item_id="CS-RAW-101",
        description="Cold Rolled Sheet 1.2mm",
        category="RAW MATERIAL",
        type_of_material="STEEL",
        supplier_name="Apex Metals Ltd",
        output_unit="KG",
        rate=Decimal("84.50"),
    )
    cons = service.upsert_single_consumable(db, cons_data, user.id)
    assert cons.item_id == "CS-RAW-101"
    assert cons.output_unit == "KG"
    assert cons.rate == Decimal("84.50")

    # Verify unit 'KG' was auto-provisioned
    unit = db.query(Unit).filter_by(code="KG").first()
    assert unit is not None
    assert cons.unit_id == unit.id

    # 2. Test single sales part upsert
    sp_data = service.SalesPartSingleCreate(
        part_no="PN-8001",
        item_id="ITM-8001",
        part_description="Outer Door Panel LH",
        uom="PCS",
    )
    sp = service.upsert_single_sales_part(db, sp_data, user.id)
    assert sp.part_number == "PN-8001"
    assert sp.item_id == "ITM-8001"
    assert sp.name == "Outer Door Panel LH"

    # 3. Test single assemble BOM upsert
    asm_data = service.AssembleSingleCreate(
        consumable_item="CS-RAW-101",
        part_no_saleable_item="PN-8001",
        used_for_name_of_saleable_part="Outer Door Panel LH",
        used_part_no_prd_order="PRD-DOOR-01",
        process_name="STAMPING",
        material_thickness_in_mm_gsm="1.20",
        no_of_process_per_part=Decimal("2.5000"),
        output_unit="KG",
        rate=Decimal("84.50"),
    )
    asm = service.upsert_single_assemble(db, asm_data, user.id)
    assert asm.consumable_item == "CS-RAW-101"
    assert asm.part_no_saleable_item == "PN-8001"
    assert asm.no_of_process_per_part == Decimal("2.5000")

    # 4. Test Header Hunter with title banner rows
    banner_rows = [
        ["KNL MANUFACTURING SOLUTIONS LTD", None, None],
        ["Report: Consumable Master Export", "Date: 2026-10-10", None],
        [None, None, None],  # Blank row
        ["Item ID", "Description", "Category", "Material Type", "Supplier Name", "Unit", "Rate"],
        ["CS-RAW-202", "Zinc Coated Strip", "COIL", "ZINC", "TATA Steel", "MTR", "125.00"],
        ["CS-RAW-303", "Hex Nut M10", "FASTENER", "STEEL", "Sundram Fasteners", "PCS", "2.15"],
    ]
    excel_bytes = make_excel_workbook(banner_rows)
    bulk_result = service.bulk_upsert_consumables(db, excel_bytes, user.id)
    assert bulk_result["total_rows"] == 2
    assert bulk_result["upserted"] == 2

    # Verify bulk items inserted
    c2 = db.query(Consumable).filter_by(item_id="CS-RAW-202").first()
    assert c2 is not None
    assert c2.output_unit == "MTR"
    c3 = db.query(Consumable).filter_by(item_id="CS-RAW-303").first()
    assert c3 is not None
    assert c3.rate == Decimal("2.15")

    # 5. Test Supplier ID extraction from Excel with source column order
    supplier_excel_rows = [
        ["Supplier ID", "Supplier name", "Item Id", "Category", "Type of material", "Description", "Output/Unit", "Rate"],
        ["SUP-99", "Tata Steel", "CS-RAW-404", "Sheet", "Steel", "Cold Rolled Coil", "KG", "88.20"],
    ]
    supp_excel_bytes = make_excel_workbook(supplier_excel_rows)
    supp_bulk_result = service.bulk_upsert_consumables(db, supp_excel_bytes, user.id)
    assert supp_bulk_result["total_rows"] == 1
    assert supp_bulk_result["upserted"] == 1

    c4 = db.query(Consumable).filter_by(item_id="CS-RAW-404").first()
    assert c4 is not None
    assert c4.supplier_id is not None
    assert c4.supplier_name == "Tata Steel"

    # 6. Test listing queries
    cons_list = service.list_consumables_table(db)
    assert cons_list["total"] >= 4
    c4_item = next(it for it in cons_list["items"] if it["item_id"] == "CS-RAW-404")
    assert c4_item["supplier_id"] == "SUP-99"
    assert c4_item["supplier_name"] == "Tata Steel"

    sp_list = service.list_sales_parts_table(db)
    assert sp_list["total"] >= 1
    assert sp_list["items"][0]["s_no"] == 1

    asm_list = service.list_assemble_table(db)
    assert asm_list["total"] >= 1

    # 7. Test bulk sales parts with trailing empty rows
    sales_parts_excel_rows = [
        ["Part No", "Item ID", "Part Description", "UOM"],
        ["PN-501", "ITM-501", "Side Panel Left", "PCS"],
        ["PN-502", "ITM-502", "Side Panel Right", "PCS"],
        [None, None, None, None],  # Empty row at bottom
        ["", "", "", ""],          # Blank row at bottom
    ]
    sp_excel_bytes = make_excel_workbook(sales_parts_excel_rows)
    sp_bulk_result = service.bulk_upsert_sales_parts(db, sp_excel_bytes, user.id)
    assert sp_bulk_result["total_rows"] == 2
    assert sp_bulk_result["upserted"] == 2
    assert len(sp_bulk_result["errors"]) == 0

    p501 = db.query(Product).filter_by(part_number="PN-501", item_id="ITM-501").first()
    assert p501 is not None
    assert p501.name == "Side Panel Left"

    # 8. Test bulk assemble BOM with missing numeric fields (rate, quantity) and trailing empty rows
    assemble_excel_rows = [
        ["Consumable Item", "Part No Saleable Item", "Saleable Part Name", "Process", "Qty", "Rate", "UOM"],
        ["CS-RAW-101", "PN-501", "Side Panel Left", "WELDING", "", "", "PCS"],  # missing qty & rate
        ["CS-RAW-202", "PN-502", "Side Panel Right", "PAINTING", "3.5", "42.50", "MTR"],
        [None, None, None, None, None, None, None],  # Trailing empty row
        ["", "", "", "", "", "", ""],                # Trailing blank row
    ]
    asm_excel_bytes = make_excel_workbook(assemble_excel_rows)
    asm_bulk_result = service.bulk_upsert_assemble(db, asm_excel_bytes, user.id)
    assert asm_bulk_result["total_rows"] == 2
    assert asm_bulk_result["upserted"] == 2
    assert len(asm_bulk_result["errors"]) == 0

    # Verify missing numeric defaults
    from app.models.mappings import ProductProcessConsumable
    asm1 = db.query(ProductProcessConsumable).filter_by(
        consumable_item="CS-RAW-101", part_no_saleable_item="PN-501"
    ).first()
    assert asm1 is not None
    assert asm1.no_of_process_per_part == Decimal("1.0000")  # Defaulted cleanly without NaN
    assert asm1.rate is None  # Defaulted to None without NaN

    asm2 = db.query(ProductProcessConsumable).filter_by(
        consumable_item="CS-RAW-202", part_no_saleable_item="PN-502"
    ).first()
    assert asm2 is not None
    assert asm2.no_of_process_per_part == Decimal("3.5000")
    assert asm2.rate == Decimal("42.50")

    # 9. Test transaction rollback recovery when an error occurs on a row
    from unittest.mock import patch
    original_ensure_unit = service.ensure_unit
    call_count = [0]

    def flaky_ensure_unit(session, uom):
        call_count[0] += 1
        if call_count[0] == 2:
            # Poison/fail row 2 explicitly
            raise RuntimeError("Simulated transient database/validation failure")
        return original_ensure_unit(session, uom)

    recovery_rows = [
        ["Part No", "Item ID", "Part Description", "UOM"],
        ["PN-701", "ITM-701", "Door Panel 1", "PCS"],
        ["PN-702", "ITM-702", "Door Panel 2", "PCS"],  # Will fail
        ["PN-703", "ITM-703", "Door Panel 3", "PCS"],  # Must succeed via rollback recovery
    ]
    rec_excel_bytes = make_excel_workbook(recovery_rows)

    with patch.object(service, "ensure_unit", side_effect=flaky_ensure_unit):
        rec_result = service.bulk_upsert_sales_parts(db, rec_excel_bytes, user.id)

    assert rec_result["total_rows"] == 3
    assert rec_result["upserted"] == 2
    assert len(rec_result["errors"]) == 1
    assert "Simulated transient" in rec_result["errors"][0]

    # Both PN-701 and PN-703 successfully committed despite row 2 failure
    assert db.query(Product).filter_by(part_number="PN-701", item_id="ITM-701").first() is not None
    assert db.query(Product).filter_by(part_number="PN-703", item_id="ITM-703").first() is not None

    # 10. Test full update, soft delete, and active listing query
    update_res = service.update_product_master_item(
        db,
        "consumables",
        cons.id,
        {"description": "Updated CR Sheet 2.0mm", "rate": Decimal("99.99")},
        user.id,
    )
    assert update_res["id"] == str(cons.id)
    assert cons.description == "Updated CR Sheet 2.0mm"
    assert cons.rate == Decimal("99.99")

    # Verify soft-delete deactivates record
    deact_res = service.deactivate_product_master_item(db, "consumables", cons.id, user.id)
    assert deact_res["is_active"] is False
    assert cons.is_active is False

    # Verify list_consumables_table filters out deactivated item
    active_list = service.list_consumables_table(db)
    assert not any(item["id"] == str(cons.id) for item in active_list["items"])

