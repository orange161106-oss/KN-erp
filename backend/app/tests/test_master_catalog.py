"""Targeted undated Product Master preview/save, count and deletion checks."""
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch
from uuid import UUID

from openpyxl import Workbook, load_workbook
import pytest
from sqlalchemy import func, select

from app.core.errors import ApplicationError
from app.models.audit import AuditLog
from app.models.master_uploads import MasterUploadBatch
from app.models.inventory_masters import Consumable, Unit
from app.schemas.master_uploads import ExistingMasterDelete, MasterCatalogSave
from app.services import master_catalog as service
from app.tests.test_master_uploads import workbook, upload
from app.tests.test_stock_statement_delete import db, identity, client_for


@pytest.mark.parametrize("category", ["consumables", "sales_parts", "assemble"])
def test_preview_does_not_save_and_explicit_save_export_delete_preserve_ids(db, category):
    content = workbook(category, rate="12")
    preview = service.preview(db, category, "synthetic.xlsx", content)
    model = service.shared.MODELS[category]
    assert preview.row_count == 1
    assert db.scalar(select(func.count()).select_from(model)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
    saved = service.save_upload(db, category, "synthetic.xlsx", content,
        MasterCatalogSave(review_token=preview.review_token), identity(db))
    assert saved.row_count == 1 and saved.filename == "synthetic.xlsx"
    db.expire_all()
    assert service.get_catalog(db, category).review_token == saved.review_token
    assert db.scalar(select(func.count()).select_from(MasterUploadBatch)) == 0
    row_id = UUID(saved.records[0]["id"])
    exported = load_workbook(BytesIO(service.export_catalog(db, category)))
    assert exported.active.max_row == 2
    exported.close()
    empty = service.delete_catalog(db, category,
        ExistingMasterDelete(review_token=saved.review_token, reason="Replace workbook"), identity(db))
    assert empty.row_count == 0 and not db.get(model, row_id).is_active
    next_preview = service.preview(db, category, "replacement.xlsx", content)
    replacement = service.save_upload(db, category, "replacement.xlsx", content,
        MasterCatalogSave(review_token=next_preview.review_token), identity(db))
    assert replacement.records[0]["id"] == str(row_id)


def counted_workbook():
    book = Workbook()
    sheet = book.active
    sheet.append(["KNL workbook"])
    sheet.append(["Item ID", "Description", "Output/Unit", "Rate", "Category"])
    sheet.append(["MAT-1", "First", "PCS", "1.1234", "First category"])
    sheet.append([None, "Missing required identifier", None, None, None])
    sheet.append(["MAT-2", "Numeric output quantity", "2000", "2.0001", "Tools"])
    sheet.append(["MAT-1", "Duplicate", "PCS", "1.1234", "Last category"])
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def test_count_report_and_numeric_units_are_visible_and_require_review(db):
    content = counted_workbook()
    preview = service.preview(db, "consumables", "synthetic.xlsx", content)
    assert preview.report == {"data_rows": 4, "identified_rows": 3, "unique_rows": 2,
        "missing_identifier_rows": [4], "duplicate_rows": [{"identifier": "MAT-1", "first_row": 3, "last_row": 6}]}
    assert len(preview.validation_errors) == 1
    assert preview.records[0]["category"] == "Last category"
    with pytest.raises(ApplicationError) as invalid:
        service.save_upload(db, "consumables", "synthetic.xlsx", content,
                            MasterCatalogSave(review_token=preview.review_token), identity(db))
    assert invalid.value.code == "INVALID_MASTER_UNIT"
    assert db.scalar(select(func.count()).select_from(Unit)) == 0
    row = next(row for row in preview.records if row["item_id"] == "MAT-2")
    saved = service.save_upload(db, "consumables", "synthetic.xlsx", content,
        MasterCatalogSave(review_token=preview.review_token, updates=[{"id": row["id"], "changes": {"output_unit": "KG"}}]), identity(db))
    material = db.get(Consumable, UUID(next(row["id"] for row in saved.records if row["item_id"] == "MAT-2")))
    assert material.rate == Decimal("2.0001") and material.output_unit == "KG"
    assert db.scalar(select(Unit).where(Unit.code == "2000")) is None
    assert not service.valid_unit("2E3")


def test_explicit_unit_column_wins_over_numeric_output_and_blank_is_not_guessed(db):
    book = Workbook()
    sheet = book.active
    sheet.append(["Item ID", "Description", "Output/Unit", "Unit", "Rate"])
    sheet.append(["MAT-1", "Explicit unit", 2000, "KG", 2])
    sheet.append(["MAT-2", "Missing reviewed unit", 1500, None, 3])
    content = BytesIO()
    book.save(content)
    book.close()
    preview = service.preview(db, "consumables", "synthetic.xlsx", content.getvalue())
    assert preview.records[0]["output_unit"] == "KG"
    assert preview.records[1]["output_unit"] == ""
    assert len(preview.validation_errors) == 1
    assert preview.validation_errors[0]["id"] == preview.records[1]["id"]


def test_existing_monthly_upload_is_visible_and_delete_rolls_back_with_history(db):
    previous = upload(db)
    catalog = service.get_catalog(db, "consumables")
    assert catalog.row_count == 1 and catalog.filename == "synthetic.xlsx"
    payload = ExistingMasterDelete(review_token=catalog.review_token, reason="Replace old upload")
    def fail():
        db.flush()
        raise RuntimeError("synthetic persistence failure")
    with patch.object(db, "commit", side_effect=fail), pytest.raises(RuntimeError):
        service.delete_catalog(db, "consumables", payload, identity(db))
    assert service.get_catalog(db, "consumables").row_count == 1
    assert db.get(MasterUploadBatch, previous.batch_id).status == "active"
    service.delete_catalog(db, "consumables", payload, identity(db))
    assert service.get_catalog(db, "consumables").row_count == 0
    assert db.get(MasterUploadBatch, previous.batch_id).status == "deleted"
    assert db.get(MasterUploadBatch, previous.batch_id).records


def test_saved_catalog_edits_use_permissions_tokens_and_protect_identifiers(db):
    previous = upload(db)
    catalog = service.get_catalog(db, "consumables")
    row_id = previous.records[0]["id"]
    payload = MasterCatalogSave(review_token=catalog.review_token,
        updates=[{"id": row_id, "changes": {"description": "Reviewed", "rate": "2.3456"}}])
    saved = service.save_changes(db, "consumables", payload, identity(db))
    assert saved.records[0]["description"] == "Reviewed"
    assert db.get(Consumable, UUID(row_id)).rate == Decimal("2.3456")
    with pytest.raises(ApplicationError) as stale:
        service.save_changes(db, "consumables", payload, identity(db))
    assert stale.value.status_code == 409
    protected = MasterCatalogSave(review_token=saved.review_token, updates=[{"id": row_id, "changes": {"item_id": "RENAME"}}])
    with pytest.raises(ApplicationError) as invalid:
        service.save_changes(db, "consumables", protected, identity(db))
    assert invalid.value.status_code == 422
    endpoint = "/api/v1/masters/product-master/consumables/workspace"
    with client_for(db, identity(db, masters_read=True)) as client:
        assert client.get(endpoint).json()["row_count"] == 1
        assert client.post(endpoint + "/preview", files={"file": ("synthetic.xlsx", workbook())}).status_code == 403
        assert client.patch(endpoint, json=payload.model_dump(mode="json")).status_code == 403
        assert client.request("DELETE", endpoint, json={"review_token": saved.review_token, "reason": "Not allowed"}).status_code == 403


def test_upload_http_preview_then_explicit_save_without_dates(db):
    endpoint = "/api/v1/masters/product-master/consumables/workspace"
    with client_for(db, identity(db, masters_create=True, masters_read=True)) as client:
        preview = client.post(endpoint + "/preview", files={"file": ("synthetic.xlsx", workbook())})
        assert preview.status_code == 200
        assert client.get(endpoint).json()["row_count"] == 0
        saved = client.post(endpoint, files={"file": ("synthetic.xlsx", workbook())},
            data={"review": MasterCatalogSave(review_token=preview.json()["review_token"]).model_dump_json()})
        assert saved.status_code == 200 and saved.json()["row_count"] == 1
        assert "month" not in saved.json() and "year" not in saved.json()
