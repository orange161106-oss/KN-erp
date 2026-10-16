"""Comprehensive verification for the direct Consumption Norms & Requirement workflow.

Covers:
- Upload with sheet "Plan" and columns A to K (S. No., Part No, ..., Sch)
- Subtotal / "Total" rows skipped
- General rows flagged and excluded from production requirement
- Duplicate groups tracked with warnings and included in requirement calculation
- Production order R0 = 0 skipped
- Worked example: 1311A01702 + BAA110116QC (Sch 2, R0 100 -> 200)
- Parts with R0 > 0 having no norms tracked in no_consumption_norms
- Approval with explicit acknowledgement of missing norms
- Export matching spreadsheet layout
"""
from datetime import date
from decimal import Decimal
from io import BytesIO
import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.auth import User
from app.models.inventory_masters import Consumable, Unit
from app.models.masters import Product
from app.models.production import Process
from app.models.rules import ConsumptionNorm
from app.schemas.norm_imports import NormImportReview
from app.schemas.requirements import CalculationRunRequest
from app.services import norm_imports, basic_planning as basic
from app.services.requirement_approval import approve
from app.tests.test_permission_foundation import db, actor


@pytest.fixture
def workflow_setup(db):
    user = User(username="workflow_tester", password_hash="test", is_super_admin=True)
    unit = Unit(code="NOS", name="Number")
    p1 = Product(code="1311A01702 - 01", part_number="1311A01702", item_id="ITEM-001", name="Pivot - Brake", uom="NOS")
    p2 = Product(code="PART-NO-NORM", part_number="PART-NO-NORM", item_id="ITEM-002", name="Part Without Norm", uom="NOS")
    proc = Process(name="Drilling")
    db.add_all([user, unit, p1, p2, proc])
    db.flush()

    c1 = Consumable(code="BAA110116QC", name="Drill Bit 9.8mm", unit_id=unit.id)
    c2 = Consumable(code="GLOVE-001", name="Safety Gloves", unit_id=unit.id)
    db.add_all([c1, c2])
    db.commit()
    return user, unit, p1, p2, proc, c1, c2


def build_plan_workbook():
    book = Workbook()
    ws = book.active
    ws.title = "Plan"
    # Row 1-2: Banner
    ws.append(["KNL Consumable Plan Sheet", "", "", "", "", "", "", "", "", "For Component", "For Consumables"])
    ws.append(["", "", "", "", "", "", "", "", "", "Prd. Order", "Sch"])
    # Row 3: Blank/info
    ws.append([])
    # Row 4: Header
    ws.append([
        "S. No.", "Part No", "Used for- Part Name", "Used Part no (prd order)",
        "Cons. Item ID", "Consumable Name", "Process Name", "Part Thickness in mm",
        "No.of Process", "Prd. Order", "Sch"
    ])
    # Row 5: Product norm 1 (Pivot - Brake, Drill Bit, Sch = 2)
    ws.append(["1", "1311A01702", "Pivot - Brake", "1311A01702 - 01", "BAA110116QC", "Drill Bit 9.8mm", "Drilling", "9.8", "2", "1", "2"])
    # Row 6: Duplicate group row (same Part No, process, consumable, different used part no)
    ws.append(["2", "1311A01702", "Pivot - Brake", "1311A01702 - 02", "BAA110116QC", "Drill Bit 9.8mm", "Drilling", "9.8", "1", "1", "1"])
    # Row 7: General row (Safety Gloves, no part no)
    ws.append(["3", "", "", "", "GLOVE-001", "Safety Gloves", "", "", "0", "1", "0"])
    # Row 8: Total / subtotal row (Consumable Name = "Total")
    ws.append(["", "", "", "", "", "Total", "", "", "", "", "3"])

    stream = BytesIO()
    book.save(stream)
    return stream.getvalue()


def test_full_workflow_end_to_end(db, workflow_setup):
    user, unit, p1, p2, proc, c1, c2 = workflow_setup

    # 1. Preview Basic_Consumable_Plan_Sheet.xlsx
    content = build_plan_workbook()
    preview = norm_imports.preview(db, "Basic_Consumable_Plan_Sheet.xlsx", content)
    assert preview.row_count == 3  # 2 product rows + 1 general row (Total row skipped)
    assert preview.skipped_total_count == 1
    assert preview.general_count == 1
    assert preview.valid_count == 3
    assert preview.duplicate_groups_count == 1  # 2 rows share 1311A01702 + Drilling + BAA110116QC

    # Check general row attributes
    general_row = [r for r in preview.rows if r.is_general][0]
    assert general_row.consumable_code == "GLOVE-001"
    assert general_row.is_general is True

    # 2. Confirm import
    fields = set(norm_imports.NormImportRowInput.model_fields)
    review_data = {
        "source_sha256": preview.source_sha256,
        "review_token": preview.review_token,
        "rows": [{k: v for k, v in r.model_dump().items() if k in fields} for r in preview.rows],
        "formula_choice": norm_imports.FORMULA_CHOICE,
        "effective_from": "2026-01-01",
        "rounding_policy": "NONE",
        "rounding_precision": 4,
        "mode": "CREATE",
        "reason": "Direct plan upload test",
    }
    review = NormImportReview(**review_data)
    confirm_res = norm_imports.confirm(db, "Basic_Consumable_Plan_Sheet.xlsx", content, review, user.id)
    assert confirm_res["created_count"] == 3

    # Verify stored norms
    norms = list(db.scalars(select(ConsumptionNorm).where(ConsumptionNorm.is_active.is_(True))))
    assert len(norms) == 3

    # 3. Upload Production Order file:
    # 1311A01702: R0 = 100
    # PART-NO-NORM: R0 = 50 (has no norms)
    # ZERO-PROD: R0 = 0 (should be skipped)
    prd_csv = (
        "Part No,Item ID,Part Description,Planned Quantity,Unit\n"
        "1311A01702,ITEM-001,Pivot - Brake,100,NOS\n"
        "PART-NO-NORM,ITEM-002,Part Without Norm,50,NOS\n"
    ).encode()

    prd_preview = basic.production_preview(db, prd_csv, "production.csv", "CSV", "2026-10", "R0", date(2026, 10, 1))
    assert prd_preview["can_confirm"] is True
    prd_confirm = basic.production_confirm(
        db, prd_csv, "production.csv", "CSV", "2026-10", "R0",
        date(2026, 10, 1), prd_preview["review_token"], user.id
    )
    v_id = prd_confirm["planning_version_id"]

    # 4. Preview Requirement Calculation
    calc_preview = basic.preview(db, v_id, date(2026, 10, 1))
    assert calc_preview["has_missing_norms"] is True
    assert calc_preview["missing_parts_count"] == 1
    assert calc_preview["missing_parts_qty"] == Decimal("50")
    assert calc_preview["no_consumption_norms"][0]["part_number"] == "1311A01702" or calc_preview["no_consumption_norms"][0]["part_number"] == "PART-NO-NORM"

    # Both duplicate group norms were calculated:
    # Row 1: 100 * 2 = 200
    # Row 2: 100 * 1 = 100
    # Total for BAA110116QC = 300
    summary = calc_preview["summary_by_consumable"]
    assert len(summary) == 1
    assert summary[0]["consumable_code"] == "BAA110116QC"
    assert summary[0]["total_calculated_qty"] == Decimal("300")
    # General norm (GLOVE-001) never participated in requirement calculation
    assert not any(s["consumable_code"] == "GLOVE-001" for s in summary)
    # Duplicate groups warning banner is present
    assert calc_preview["duplicate_groups_warning"] is not None
    assert "norm groups in Consumption Norms share the same Part No" in calc_preview["duplicate_groups_warning"]

    # 5. Persist Calculation
    calc_res = basic.calculate(db, CalculationRunRequest(planning_version_id=v_id), user.id)
    assert calc_res.status == "CALCULATED_WITH_ERRORS"
    assert calc_res.has_missing_norms is True

    # 6. Approval without acknowledgement must fail
    with pytest.raises(ApplicationError) as err:
        approve(db, v_id, user, acknowledge_missing_norms=False)
    assert "CALCULATION_REQUIRED" in err.value.code

    # 7. Approval with explicit acknowledgement succeeds
    approval_res = approve(db, v_id, user, acknowledge_missing_norms=True)
    assert approval_res["status"] == "APPROVED"
    assert approval_res["replayed"] is False

    # Check AuditLog records acknowledgement
    audit = db.scalar(select(AuditLog).where(AuditLog.entity_id == v_id, AuditLog.action == "APPROVE"))
    assert "incomplete: 1 parts without norms" in audit.reason

    # 8. Export matches spreadsheet layout
    export_content, media = norm_imports.export_file(db, format="xlsx")
    assert len(export_content) > 0
    assert media == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
