"""Norm maintenance and import safety checks against a disposable SQLite database."""
import csv
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
import pytest
from sqlalchemy import event, select

from app.core.errors import ApplicationError, register_error_handlers
from app.db.session import get_db
from app.models.audit import AuditLog
from app.models.auth import User
from app.models.inventory_masters import Consumable, Unit
from app.models.masters import Product
from app.models.production import Process
from app.models.rules import ConsumptionNorm
from app.modules.rules.router import router
from app.schemas.auth import CurrentUser
from app.schemas.norm_imports import NormImportCorrections, NormImportReview
from app.schemas.rules import ConsumptionNormCreate, ConsumptionNormUpdate, ConsumptionNormBatchUpdate
from app.security.dependencies import get_current_user
from app.services import norm_imports, rules
from app.tests.test_permission_foundation import db


@pytest.fixture
def masters(db):
    actor = User(username="norm_reviewer", password_hash="synthetic")
    unit = Unit(code="NOS", name="Number")
    product = Product(code="PROD-1", part_number="1311A01702 - 01", item_id="ITEM-1", name="Pivot - Brake", uom="PCS")
    process = Process(name="Drilling")
    db.add_all([actor, unit, product, process]); db.flush()
    material = Consumable(code="BAA110116QC", name="Drill Bit", unit_id=unit.id)
    db.add(material); db.commit()
    return actor, product, process, material, unit


def contents(rows=None, format="xlsx"):
    rows = rows or [["1311A01702", "Pivot - Brake", "1311A01702 - 01", "BAA110116QC", "Drill Bit", "Drilling", "9.8", "2", "100", "200"]]
    headers = [values[0] for values in norm_imports.FIELDS.values()]
    if format == "csv":
        stream = StringIO(); writer = csv.writer(stream); writer.writerow(headers); writer.writerows(rows)
        return stream.getvalue().encode("utf-8-sig")
    book = Workbook(); book.active.title = "Plan"
    book.active.append(["KNL approved source reference"]); book.active.append(["Parameters"])
    book.active.append(headers)
    for row in rows: book.active.append(row)
    stream = BytesIO(); book.save(stream); return stream.getvalue()


def reviewed(preview, **changes):
    fields = set(norm_imports.NormImportRowInput.model_fields)
    values = {"source_sha256": preview.source_sha256, "review_token": preview.review_token,
        "rows": [{key: value for key, value in row.model_dump().items() if key in fields} for row in preview.rows],
        "formula_choice": norm_imports.FORMULA_CHOICE, "effective_from": "2026-10-01", "rounding_policy": "NONE",
        "rounding_precision": 4, "mode": "CREATE", "reason": "Explicit approved Q times process count import"}
    values.update(changes)
    return NormImportReview(**values)


@pytest.mark.parametrize("format", ["xlsx", "csv"])
def test_preview_is_read_only_and_confirm_uses_approved_final_quantity(db, masters, format):
    actor, product, process, material, unit = masters
    source = contents(format=format)
    preview = norm_imports.preview(db, f"norms.{format}", source)
    assert preview.row_count == preview.valid_count == 1
    assert db.scalar(select(ConsumptionNorm)) is None
    assert db.scalar(select(AuditLog)) is None
    assert preview.rows[0].unit_code == "NOS"
    result = norm_imports.confirm(db, f"norms.{format}", source, reviewed(preview), actor.id)
    assert result["created_count"] == 1
    saved = result["records"][0]
    assert saved.plant_id is None and saved.parameters["rate"] == "2"
    assert saved.reference_data["reference_production_qty"] == "100"
    evaluation = rules.evaluate_consumption_norm(db, __import__("app.schemas.rules", fromlist=["EvaluationRequest"]).EvaluationRequest(
        product_id=product.id, process_id=process.id, consumable_id=material.id, production_quantity=Decimal("100"), as_of_date=date(2026, 10, 1)))
    assert evaluation.calculation.final_calculated_requirement == Decimal("200")


def test_repeat_confirm_is_idempotent(db, masters):
    actor, *_ = masters; source = contents()
    preview = norm_imports.preview(db, "norms.xlsx", source); review = reviewed(preview)
    first = norm_imports.confirm(db, "norms.xlsx", source, review, actor.id)
    again = norm_imports.confirm(db, "norms.xlsx", source, review, actor.id)
    assert again["replayed"] is True and again["records"][0].id == first["records"][0].id
    assert len(list(db.scalars(select(ConsumptionNorm)))) == 1


@pytest.mark.parametrize("field,value,code", [(2, "MISSING", "MASTER_REFERENCE_REQUIRED"), (3, "BAD-MATERIAL", "MASTER_REFERENCE_REQUIRED"),
    (7, "=I4*J4", "INVALID_NORM_NUMBER"), (7, "0", "INVALID_NORM_NUMBER"), (7, "-1", "INVALID_NORM_NUMBER")])
def test_invalid_rows_block_all_persistence(db, masters, field, value, code):
    actor, *_ = masters
    rows = [["1311A01702", "Pivot - Brake", "1311A01702 - 01", "BAA110116QC", "Drill Bit", "Drilling", "9.8", "2", "100", "200"]]
    rows[0][field] = value; source = contents(rows)
    preview = norm_imports.preview(db, "norms.xlsx", source)
    assert preview.invalid_count == 1 and code in [error.code for error in preview.rows[0].errors]
    with pytest.raises(ApplicationError) as failure:
        norm_imports.confirm(db, "norms.xlsx", source, reviewed(preview), actor.id)
    assert failure.value.code == "NORM_IMPORT_VALIDATION_FAILED"
    assert db.scalar(select(ConsumptionNorm)) is None


def test_duplicate_rows_are_not_silently_merged(db, masters):
    row = ["1311A01702", "Pivot", "1311A01702 - 01", "BAA110116QC", "Bit", "Drilling", "9.8", "2", "100", "200"]
    preview = norm_imports.preview(db, "norms.xlsx", contents([row, row]))
    assert preview.duplicate_count == 2 and preview.invalid_count == 2


def test_review_corrections_revalidate_without_writes(db, masters):
    source = contents([["1311A01702", "Pivot", "UNKNOWN", "BAA110116QC", "Bit", "Drilling", "9.8", "2", "100", "200"]])
    first = norm_imports.preview(db, "norms.xlsx", source)
    changes = reviewed(first).model_dump(include={"source_sha256", "rows"})
    changes["rows"][0]["used_part_number"] = "1311A01702 - 01"
    preview = norm_imports.preview(db, "norms.xlsx", source, NormImportCorrections(**changes))
    assert preview.valid_count == 1 and db.scalar(select(ConsumptionNorm)) is None
    changes["rows"] = []
    with pytest.raises(ValueError): NormImportCorrections(**changes)


def test_existing_skip_and_explicit_supersede_preserve_versions(db, masters):
    actor, *_ = masters; source = contents()
    first = norm_imports.preview(db, "norms.xlsx", source)
    saved = norm_imports.confirm(db, "norms.xlsx", source, reviewed(first), actor.id)["records"][0]
    preview = norm_imports.preview(db, "renamed.xlsx", source)
    assert preview.existing_count == 1
    result = norm_imports.confirm(db, "renamed.xlsx", source, reviewed(preview), actor.id)
    assert result["skipped_count"] == 1 and result["created_count"] == 0
    changed = contents([["1311A01702", "Pivot", "1311A01702 - 01", "BAA110116QC", "Bit", "Drilling", "9.8", "3", "100", "300"]])
    preview = norm_imports.preview(db, "new.xlsx", changed)
    assert preview.conflict_count == 1
    with pytest.raises(ApplicationError):
        norm_imports.confirm(db, "new.xlsx", changed, reviewed(preview), actor.id)
    result = norm_imports.confirm(db, "new.xlsx", changed, reviewed(preview, mode="SUPERSEDE"), actor.id)
    assert result["superseded_count"] == 1
    assert db.get(ConsumptionNorm, saved.id).is_active is False
    assert result["records"][0].version == 2


def test_stale_review_rejects_new_master_state(db, masters):
    actor, product, *_ = masters; source = contents()
    preview = norm_imports.preview(db, "norms.xlsx", source)
    product.code = "CHANGED-CODE"; db.commit()
    with pytest.raises(ApplicationError) as failure:
        norm_imports.confirm(db, "norms.xlsx", source, reviewed(preview), actor.id)
    assert failure.value.code == "STALE_NORM_REVIEW" and db.scalar(select(ConsumptionNorm)) is None


def test_edit_creates_version_and_process_coefficient_changes_atomically(db, masters):
    actor, *_ = masters; source = contents(); preview = norm_imports.preview(db, "norms.xlsx", source)
    saved = norm_imports.confirm(db, "norms.xlsx", source, reviewed(preview), actor.id)["records"][0]
    replacement = rules.update_consumption_norm(db, saved.id, ConsumptionNormUpdate(expected_version=1, reference_data={"process_count": "3"}), actor_id=actor.id)
    assert replacement.id != saved.id and replacement.version == 2
    assert replacement.parameters["rate"] == "3"
    assert db.get(ConsumptionNorm, saved.id).parameters["rate"] == "2"
    assert replacement.reference_data["source_sha256"] == preview.source_sha256
    with pytest.raises(ApplicationError):
        rules.update_consumption_norm(db, saved.id, ConsumptionNormUpdate(parameters={"rate": "4"}), actor_id=actor.id)


def test_bulk_update_fatal_error_rolls_back_every_replacement(db, masters):
    actor, *_ = masters; source = contents(); preview = norm_imports.preview(db, "norms.xlsx", source)
    saved = norm_imports.confirm(db, "norms.xlsx", source, reviewed(preview), actor.id)["records"][0]
    updates = [{"norm_id": str(saved.id), "expected_version": 1, "rounding_precision": 2},
        {"norm_id": str(uuid4()), "expected_version": 1, "rounding_precision": 2}]
    with pytest.raises(ApplicationError):
        rules.bulk_update_consumption_norms(db, ConsumptionNormBatchUpdate(updates=updates, reason="Reviewed change"), actor.id)
    assert len(list(db.scalars(select(ConsumptionNorm)))) == 1 and db.get(ConsumptionNorm, saved.id).is_active


def test_template_export_and_empty_missing_headers(db, masters):
    for format in ("xlsx", "csv"):
        template, media = norm_imports.export_file(format=format, template=True)
        assert template and media
        with pytest.raises(ApplicationError) as failure:
            norm_imports.preview(db, f"empty.{format}", template)
        assert failure.value.code == "EMPTY_NORM_FILE"
    with pytest.raises(ApplicationError) as failure:
        norm_imports.preview(db, "bad.csv", b"Wrong Header\nabc\n")
    assert failure.value.code == "MISSING_NORM_COLUMNS"


def test_norm_router_read_flag_never_authorizes_import_or_edit(db, masters):
    actor, *_ = masters
    identity = CurrentUser(id=actor.id, username=actor.username, roles=[], permissions=['norms.write'], consumption_norms_read=True)
    app = FastAPI(); register_error_handlers(app); app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: identity
    with TestClient(app) as client:
        assert client.get("/api/v1/consumption-norms/template").status_code == 200
        assert client.post("/api/v1/consumption-norms/import-preview", files={"file": ("norms.xlsx", contents())}).status_code == 403
        identity.consumption_norms_create = True
        preview = client.post("/api/v1/consumption-norms/import-preview", files={"file": ("norms.xlsx", contents())})
        assert preview.status_code == 200


def test_bounded_min_max_creation_preserves_its_existing_formula_branch(db, masters):
    actor, product, process, material, unit = masters
    saved = rules.create_consumption_norm(db, ConsumptionNormCreate(rule_type='MIN_MAX',product_id=product.id,
        process_id=process.id,consumable_id=material.id,unit_id=unit.id,effective_from=date(2026,10,1),
        parameters={'base_rate':'2','min_quantity':'10','max_quantity':'150'}), actor_id=actor.id)
    assert not {'msl_days','moq','current_stock'} & saved.parameters.keys()
    from app.domain.rules import RuleCalculationInput, evaluate_rule
    assert evaluate_rule(RuleCalculationInput(rule_type='MIN_MAX',rule_version=1,parameters=saved.parameters,
        production_quantity=Decimal('100'),unit=unit.code)).final_calculated_requirement == Decimal('150')


def test_imported_rate_cannot_drift_from_the_reviewed_process_count(db, masters):
    actor, *_ = masters; content = contents(); preview = norm_imports.preview(db,'norms.xlsx',content)
    saved = norm_imports.confirm(db,'norms.xlsx',content,reviewed(preview),actor.id)['records'][0]
    with pytest.raises(ApplicationError) as failure:
        rules.update_consumption_norm(db,saved.id,ConsumptionNormUpdate(parameters={'rate':'99','scrap_factor':'0'}),actor_id=actor.id)
    assert failure.value.code == 'NORM_RATE_CONFLICT'
    with pytest.raises(ApplicationError) as failure:
        rules.update_consumption_norm(db,saved.id,ConsumptionNormUpdate(parameters={'rate':'2','scrap_factor':'0.1'}),actor_id=actor.id)
    assert failure.value.code == 'NORM_APPROVED_FORMULA_CONFLICT'
    assert db.get(ConsumptionNorm,saved.id).parameters['rate'] == '2'


def test_bulk_import_batches_master_and_version_reads(db, masters):
    actor, *_ = masters
    db.add_all([Process(name=f'Operation {index}') for index in range(20)]);db.commit()
    content = contents([['BASE','Reference','1311A01702 - 01','BAA110116QC','Bit',f'Operation {index}','9.8','2','1','2'] for index in range(20)])
    preview = norm_imports.preview(db,'batch.xlsx',content)
    queries = []
    def record(_connection,_cursor,statement,*_args):
        if statement.lstrip().upper().startswith('SELECT'): queries.append(statement)
    event.listen(db.get_bind(),'before_cursor_execute',record)
    try:
        result = norm_imports.confirm(db,'batch.xlsx',content,reviewed(preview),actor.id)
    finally:
        event.remove(db.get_bind(),'before_cursor_execute',record)
    assert result['created_count'] == 20 and len(result['records']) == 20
    assert len(queries) <= 10


def test_text_thickness_is_stored_as_reference_text_without_error(db, masters):
    actor, *_ = masters
    # Test non-numeric thickness e.g. 'OD22.23 x T 2'
    row_text = ["1311A01702", "Pivot - Brake", "1311A01702 - 01", "BAA110116QC", "Drill Bit", "Drilling", "OD22.23 x T 2", "2", "100", "200"]
    source = contents([row_text])
    preview = norm_imports.preview(db, "norms.xlsx", source)
    assert preview.valid_count == 1
    assert preview.invalid_count == 0
    assert preview.rows[0].thickness == "OD22.23 x T 2"
    assert len(preview.rows[0].errors) == 0

    result = norm_imports.confirm(db, "norms.xlsx", source, reviewed(preview), actor.id)
    assert result["created_count"] == 1
    saved = result["records"][0]
    assert saved.reference_data["thickness"] == "OD22.23 x T 2"

    # Test numeric thickness e.g. '9.8'
    row_num = ["1311A01702", "Pivot - Brake", "1311A01702 - 01", "BAA110116QC", "Drill Bit", "Drilling", "9.8", "2", "100", "200"]
    source_num = contents([row_num])
    preview_num = norm_imports.preview(db, "norms_num.xlsx", source_num)
    assert preview_num.valid_count == 1
    assert preview_num.rows[0].thickness == "9.8"


def test_confirm_skip_invalid_imports_valid_rows_and_skips_invalid_rows(db, masters):
    actor, *_ = masters
    valid_row = ["1311A01702", "Pivot - Brake", "1311A01702 - 01", "BAA110116QC", "Drill Bit", "Drilling", "OD22.23 x T 2", "2", "100", "200"]
    invalid_row = ["1311A01702", "Pivot - Brake", "1311A01702 - 01", "NON_EXISTENT_CODE", "Unknown", "Drilling", "1.0", "2", "100", "200"]
    source = contents([valid_row, invalid_row])
    preview = norm_imports.preview(db, "norms.xlsx", source)

    assert preview.row_count == 2
    assert preview.valid_count == 1
    assert preview.invalid_count == 1

    # Confirm with skip_invalid=False must fail with NORM_IMPORT_VALIDATION_FAILED
    with pytest.raises(ApplicationError) as failure:
        norm_imports.confirm(db, "norms.xlsx", source, reviewed(preview, skip_invalid=False), actor.id)
    assert failure.value.code == "NORM_IMPORT_VALIDATION_FAILED"
    assert db.scalar(select(ConsumptionNorm)) is None

    # Confirm with skip_invalid=True must succeed, importing valid row and skipping invalid
    result = norm_imports.confirm(db, "norms.xlsx", source, reviewed(preview, skip_invalid=True), actor.id)
    assert result["created_count"] == 1
    assert result["skipped_invalid_count"] == 1
    assert "1 invalid rows skipped" in result["message"]

    # Verify only the valid row is persisted
    norms_in_db = list(db.scalars(select(ConsumptionNorm)))
    assert len(norms_in_db) == 1
    assert result["records"][0].reference_data["thickness"] == "OD22.23 x T 2"
    ref_map = rules.norm_reference_data(db, [norms_in_db[0].id])
    assert ref_map[norms_in_db[0].id]["thickness"] == "OD22.23 x T 2"


def test_strict_true_errors(db, masters):
    actor, *_ = masters

    # 1. Blank Cons. Item ID
    blank_cons = ["1311A01702", "Pivot - Brake", "1311A01702 - 01", "", "Drill Bit", "Drilling", "1.0", "2", "100", "200"]
    preview1 = norm_imports.preview(db, "norms.xlsx", contents([blank_cons]))
    assert preview1.invalid_count == 1
    codes1 = [e.code for e in preview1.rows[0].errors]
    assert "CONSUMABLE_CODE_REQUIRED" in codes1

    # 2. Cons. Item ID is numeric '1' or '2'
    numeric_cons = ["1311A01702", "Pivot - Brake", "1311A01702 - 01", "1", "Drill Bit", "Drilling", "1.0", "2", "100", "200"]
    preview2 = norm_imports.preview(db, "norms.xlsx", contents([numeric_cons]))
    assert preview2.invalid_count == 1
    codes2 = [e.code for e in preview2.rows[0].errors]
    assert "INVALID_CONSUMABLE_CODE" in codes2

    # 3. Blank Part No on a product-linked row
    blank_part = ["", "Pivot - Brake", "1311A01702 - 01", "BAA110116QC", "Drill Bit", "Drilling", "1.0", "2", "100", "200"]
    preview3 = norm_imports.preview(db, "norms.xlsx", contents([blank_part]))
    assert preview3.invalid_count == 1
    codes3 = [e.code for e in preview3.rows[0].errors]
    assert "BLANK_PART_NUMBER" in codes3
