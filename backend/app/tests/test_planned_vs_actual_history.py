from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.auth import Role, User
from app.models.inventory import StockImportBatch, StockTransaction
from app.models.inventory_masters import Consumable, Unit
from app.models.plant_workflow import RequirementAdjustment
from app.models.prd import ImportBatch, PlanningVersion, PRDOrderHeader, PRDOrderItem
from app.models.production import Plant, Process
from app.models.requirements import CalculatedRequirement
from app.models.rules import ConsumptionNorm
from app.security.tokens import create_access_token

TEST_SIGNING_KEY = "synthetic-test-key-never-use-in-production-0123456789"


@pytest.fixture
def history_fixture():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def register_sqlite_functions(dbapi_connection, connection_record):
        dbapi_connection.create_function("btrim", 1, lambda s: s.strip() if s is not None else None)

    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_factory()

    # 1. User & Auth
    admin_role = Role(id=uuid4(), code="ADMIN", name="Admin Role")
    user = User(
        id=uuid4(),
        username="report_tester",
        password_hash="dummy_hash",
        is_active=True,
        roles=[admin_role],
    )
    db.add(user)

    # 2. Units
    u_box = Unit(id=uuid4(), code="BOX", name="Carton Box", is_active=True)
    u_roll = Unit(id=uuid4(), code="ROLL", name="Tape Roll", is_active=True)
    u_l = Unit(id=uuid4(), code="L", name="Liter", is_active=True)
    u_pcs = Unit(id=uuid4(), code="PCS", name="Pieces", is_active=True)
    db.add_all([u_box, u_roll, u_l, u_pcs])

    # 3. Consumables
    cons_box = Consumable(
        id=uuid4(),
        code="CONS-BOX-M25",
        name="Master Shipping Carton",
        unit_id=u_box.id,
        is_active=True,
    )
    cons_tape = Consumable(
        id=uuid4(),
        code="CONS-TAPE-PVC",
        name="PVC Packaging Tape",
        unit_id=u_roll.id,
        is_active=True,
    )
    cons_solvent = Consumable(
        id=uuid4(),
        code="CONS-SOLV-IPA",
        name="IPA Solvent 99%",
        unit_id=u_l.id,
        is_active=True,
    )
    db.add_all([cons_box, cons_tape, cons_solvent])

    # 4. Plant & Process
    plant1 = Plant(id=uuid4(), name="Plant Pune 01", location="Pune, Maharashtra", is_active=True)
    plant2 = Plant(id=uuid4(), name="Plant Chennai 01", location="Chennai, Tamil Nadu", is_active=True)
    proc_pack = Process(id=uuid4(), name="Final Packaging", description="Packaging line", is_active=True)
    proc_clean = Process(id=uuid4(), name="Surface Cleaning", description="Cleaning line", is_active=True)
    db.add_all([plant1, plant2, proc_pack, proc_clean])
    db.flush()

    # 5. Consumption Norms (for immutability checking)
    norm = ConsumptionNorm(
        id=uuid4(),
        rule_type="PACKING_RATIO",
        consumable_id=cons_box.id,
        version=1,
        parameters={"units_per_pack": 25},
        unit_id=u_box.id,
        rounding_policy="ROUND_UP",
        rounding_precision=0,
        effective_from=date(2026, 10, 1),
        is_active=True,
    )
    db.add(norm)

    # 6. Planning Version (2026-10)
    version = PlanningVersion(
        id=uuid4(),
        planning_period="2026-10",
        version_number=0,
        revision_label="R0",
        source_filename="PRD_2026_10.xlsx",
        status="CALCULATED",
        created_by=user.id,
    )
    db.add(version)
    db.flush()

    # Dummy PRD order items for foreign key relations
    batch = ImportBatch(
        id=uuid4(),
        planning_version_id=version.id,
        filename="PRD_2026_10.xlsx",
        file_size_bytes=1024,
        status="PROMOTED",
        uploaded_by=user.id,
    )
    db.add(batch)
    db.flush()

    header = PRDOrderHeader(
        id=uuid4(),
        planning_version_id=version.id,
        import_batch_id=batch.id,
        planning_period="2026-10",
        total_planned_qty=Decimal("1000.0000"),
        total_line_items=1,
    )
    db.add(header)
    db.flush()

    prd_item = PRDOrderItem(
        id=uuid4(),
        planning_version_id=version.id,
        header_id=header.id,
        source_row_number=1,
        product_code="PRD-HARNESS-01",
        product_id=uuid4(),  # dummy
        plant_code="PLANT-PUNE-01",
        planned_quantity=Decimal("1000.0000"),
        uom="PCS",
        target_period="2026-10",
    )
    # Insert with raw dummy product
    from app.models.masters import Product
    prod = Product(id=prd_item.product_id, code="PRD-HARNESS-01", name="Harness", uom="PCS", is_active=True)
    db.add(prod)
    db.add(prd_item)
    db.flush()

    # 7. Calculated Requirements:
    # Item 1: Box -> 1000 BOX
    req_box = CalculatedRequirement(
        id=uuid4(),
        planning_version_id=version.id,
        prd_order_item_id=prd_item.id,
        product_id=prod.id,
        plant_id=plant1.id,
        process_id=proc_pack.id,
        consumable_id=cons_box.id,
        rule_id=norm.id,
        rule_type="PACKING_RATIO",
        rule_version=1,
        parameters={"units_per_pack": 25},
        source_production_qty=Decimal("25000.0000"),
        raw_requirement=Decimal("1000.0000"),
        rounding_policy="ROUND_UP",
        rounding_precision=0,
        calculated_qty=Decimal("1000.0000"),
        unit_id=u_box.id,
        uom="BOX",
        calculation_steps=[],
        explanation_payload={},
    )
    # Item 2: Tape -> 500 ROLL
    req_tape = CalculatedRequirement(
        id=uuid4(),
        planning_version_id=version.id,
        prd_order_item_id=prd_item.id,
        product_id=prod.id,
        plant_id=plant1.id,
        process_id=proc_pack.id,
        consumable_id=cons_tape.id,
        rule_id=norm.id,
        rule_type="PACKING_RATIO",
        rule_version=1,
        parameters={"units_per_pack": 50},
        source_production_qty=Decimal("25000.0000"),
        raw_requirement=Decimal("500.0000"),
        rounding_policy="ROUND_UP",
        rounding_precision=0,
        calculated_qty=Decimal("500.0000"),
        unit_id=u_roll.id,
        uom="ROLL",
        calculation_steps=[],
        explanation_payload={},
    )
    # Item 3: Solvent -> 200 L
    req_solvent = CalculatedRequirement(
        id=uuid4(),
        planning_version_id=version.id,
        prd_order_item_id=prd_item.id,
        product_id=prod.id,
        plant_id=plant1.id,
        process_id=proc_clean.id,
        consumable_id=cons_solvent.id,
        rule_id=norm.id,
        rule_type="PACKING_RATIO",
        rule_version=1,
        parameters={},
        source_production_qty=Decimal("25000.0000"),
        raw_requirement=Decimal("200.0000"),
        rounding_policy="NONE",
        rounding_precision=2,
        calculated_qty=Decimal("200.0000"),
        unit_id=u_l.id,
        uom="L",
        calculation_steps=[],
        explanation_payload={},
    )
    db.add_all([req_box, req_tape, req_solvent])

    # 8. Approved Adjustments (M3.4/M3.5): Box has +50 BOX approved
    adj_box = RequirementAdjustment(
        id=uuid4(),
        planning_version_id=version.id,
        plant_id=plant1.id,
        consumable_id=cons_box.id,
        category="SPECIAL",
        requested_qty=Decimal("50.0000"),
        uom="BOX",
        reason="Export packaging additional reinforcement",
        requested_by=user.id,
        status="APPROVED",
    )
    db.add(adj_box)

    # 9. Stock Transactions in October 2026 (Central Store Ledger M4.1)
    stock_batch = StockImportBatch(
        id=uuid4(),
        export_id="EXP-2026-10-OCT",
        payload_hash="dummy_hash",
        generated_at=datetime(2026, 10, 31, 18, 0, tzinfo=timezone.utc),
        imported_by=user.id,
        import_reason="Monthly stock movements import",
        movement_count=3,
        snapshot_count=0,
    )
    db.add(stock_batch)
    db.flush()

    # Box: ISSUE 1200, RETURN 100 -> Net Actual = 1100 BOX
    tx1_box = StockTransaction(
        id=uuid4(),
        source_event_id="EVT-BOX-01",
        payload_hash="hash1",
        batch_id=stock_batch.id,
        consumable_id=cons_box.id,
        unit_id=u_box.id,
        source_unit_id=u_box.id,
        source_quantity=Decimal("1200.0000"),
        conversion_factor=Decimal("1.000000000000"),
        movement="ISSUE",
        quantity=Decimal("1200.0000"),
        signed_quantity=Decimal("-1200.0000"),
        event_at=datetime(2026, 10, 15, 10, 30, tzinfo=timezone.utc),
        source_actor="Store Keeper",
    )
    tx2_box = StockTransaction(
        id=uuid4(),
        source_event_id="EVT-BOX-02",
        payload_hash="hash2",
        batch_id=stock_batch.id,
        consumable_id=cons_box.id,
        unit_id=u_box.id,
        source_unit_id=u_box.id,
        source_quantity=Decimal("100.0000"),
        conversion_factor=Decimal("1.000000000000"),
        movement="RETURN",
        quantity=Decimal("100.0000"),
        signed_quantity=Decimal("100.0000"),
        event_at=datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc),
        source_actor="Store Keeper",
    )
    # Tape: ISSUE 400, no return -> Net Actual = 400 ROLL
    tx3_tape = StockTransaction(
        id=uuid4(),
        source_event_id="EVT-TAPE-01",
        payload_hash="hash3",
        batch_id=stock_batch.id,
        consumable_id=cons_tape.id,
        unit_id=u_roll.id,
        source_unit_id=u_roll.id,
        source_quantity=Decimal("400.0000"),
        conversion_factor=Decimal("1.000000000000"),
        movement="ISSUE",
        quantity=Decimal("400.0000"),
        signed_quantity=Decimal("-400.0000"),
        event_at=datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc),
        source_actor="Store Keeper",
    )
    # (Solvent has NO stock transactions in October 2026)
    # Box: RECEIPT 5000 (Supplier delivery / GRN receipt) -> positive stock receipt, NEVER counted as consumption!
    tx_receipt_box = StockTransaction(
        id=uuid4(),
        source_event_id="EVT-BOX-REC-01",
        payload_hash="hash_rec",
        batch_id=stock_batch.id,
        consumable_id=cons_box.id,
        unit_id=u_box.id,
        source_unit_id=u_box.id,
        source_quantity=Decimal("5000.0000"),
        conversion_factor=Decimal("1.000000000000"),
        movement="RECEIPT",
        quantity=Decimal("5000.0000"),
        signed_quantity=Decimal("5000.0000"),
        event_at=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc),
        source_actor="Store Inward",
    )
    db.add_all([tx1_box, tx2_box, tx3_tape, tx_receipt_box])
    db.commit()

    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url="postgresql+psycopg://test_user:pass@127.0.0.1/kn_unit_test",
        auth_secret_key=TEST_SIGNING_KEY,
    )
    app = create_app(settings)
    app.dependency_overrides[get_db] = lambda: db

    with TestClient(app, raise_server_exceptions=True) as client:
        token = create_access_token(user.id, settings)
        headers = {"Authorization": f"Bearer {token}"}
        ctx = {
            "version": version,
            "cons_box": cons_box,
            "cons_tape": cons_tape,
            "cons_solvent": cons_solvent,
            "plant1": plant1,
            "plant2": plant2,
            "proc_pack": proc_pack,
            "proc_clean": proc_clean,
            "norm": norm,
        }
        yield client, db, headers, ctx

    db.close()
    Base.metadata.drop_all(bind=engine)


# ==============================================================================
# TESTS FOR M6.1 PLANNED VS ACTUAL CONSUMPTION HISTORY
# ==============================================================================

def test_planned_vs_actual_complete_lineage(history_fixture):
    """Lineage: Calculated Requirement + Approved Additions = Final Requirement.
    Actual stock consumption (ISSUE - RETURN) produces exact variance amount and %.
    """
    client, db, headers, ctx = history_fixture

    resp = client.get(
        "/api/v1/reports/planned-vs-actual",
        headers=headers,
        params={"period": "2026-10"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["period"] == "2026-10"
    assert data["revision_label"] == "R0"
    assert len(data["items"]) == 3

    # Find Box item
    box_item = next(it for it in data["items"] if it["consumable_code"] == "CONS-BOX-M25")
    assert Decimal(str(box_item["calculated_qty"])) == Decimal("1000.0000")
    assert Decimal(str(box_item["approved_additions_qty"])) == Decimal("50.0000")
    assert Decimal(str(box_item["final_required_qty"])) == Decimal("1050.0000")

    # Net Actual Consumed = 1200 (ISSUE) - 100 (RETURN) = 1100
    assert Decimal(str(box_item["actual_consumed_qty"])) == Decimal("1100.0000")
    assert box_item["actual_status"] == "AVAILABLE"

    # Variance Amount = 1100 - 1050 = +50.0000
    assert Decimal(str(box_item["variance_amount"])) == Decimal("50.0000")
    # Variance % = (50 / 1050) * 100 = 4.76%
    assert Decimal(str(box_item["variance_percentage"])) == Decimal("4.76")


def test_favorable_variance_under_consumption(history_fixture):
    """Under-consumption produces negative variance amount and negative variance % (savings)."""
    client, db, headers, ctx = history_fixture

    resp = client.get(
        "/api/v1/reports/planned-vs-actual",
        headers=headers,
        params={"period": "2026-10", "consumable_id": str(ctx["cons_tape"].id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 1
    tape = data["items"][0]

    assert Decimal(str(tape["calculated_qty"])) == Decimal("500.0000")
    assert Decimal(str(tape["approved_additions_qty"])) == Decimal("0.0000")
    assert Decimal(str(tape["final_required_qty"])) == Decimal("500.0000")

    # Actual = 400 ROLL
    assert Decimal(str(tape["actual_consumed_qty"])) == Decimal("400.0000")
    assert tape["actual_status"] == "AVAILABLE"

    # Variance Amount = 400 - 500 = -100.0000
    assert Decimal(str(tape["variance_amount"])) == Decimal("-100.0000")
    # Variance % = (-100 / 500) * 100 = -20.00%
    assert Decimal(str(tape["variance_percentage"])) == Decimal("-20.00")


def test_missing_stock_transactions_reports_null_not_inferred(history_fixture):
    """When stock movements are absent, actual_consumed_qty is null (NO_STOCK_DATA), never inferred as 0."""
    client, db, headers, ctx = history_fixture

    resp = client.get(
        "/api/v1/reports/planned-vs-actual",
        headers=headers,
        params={"period": "2026-10", "consumable_id": str(ctx["cons_solvent"].id)},
    )
    assert resp.status_code == 200
    solvent = resp.json()["items"][0]

    assert Decimal(str(solvent["final_required_qty"])) == Decimal("200.0000")
    assert solvent["actual_consumed_qty"] is None
    assert solvent["variance_amount"] is None
    assert solvent["variance_percentage"] is None
    assert solvent["actual_status"] == "NO_STOCK_DATA"


def test_purchase_and_grn_strictly_excluded_from_consumption(history_fixture):
    """Purchase orders and GRN receipts are procurement/inbound logistics, NEVER counted as consumption."""
    client, db, headers, ctx = history_fixture

    resp = client.get(
        "/api/v1/reports/planned-vs-actual",
        headers=headers,
        params={"period": "2026-10", "consumable_id": str(ctx["cons_box"].id)},
    )
    assert resp.status_code == 200
    box_item = resp.json()["items"][0]

    # PO was 5000, GRN was 5000, but actual consumption is strictly the net stock issue of 1100
    assert Decimal(str(box_item["actual_consumed_qty"])) == Decimal("1100.0000")
    assert Decimal(str(box_item["actual_consumed_qty"])) != Decimal("5000.0000")
    assert Decimal(str(box_item["actual_consumed_qty"])) != Decimal("6100.0000")


def test_filters_by_plant_and_process_mark_grain_unavailable(history_fixture):
    """Filtering by plant or process flags actual as unavailable due to central ledger grain (TBD-1 & 2)."""
    client, db, headers, ctx = history_fixture

    # 1. Filter by plant
    resp_plant = client.get(
        "/api/v1/reports/planned-vs-actual",
        headers=headers,
        params={"period": "2026-10", "plant_id": str(ctx["plant1"].id)},
    )
    assert resp_plant.status_code == 200
    plant_items = resp_plant.json()["items"]
    assert len(plant_items) > 0
    for it in plant_items:
        assert it["plant_name"] == "Plant Pune 01"
        assert it["actual_consumed_qty"] is None
        assert it["actual_status"] == "PLANT_GRAIN_UNAVAILABLE"

    # 2. Filter by process
    resp_proc = client.get(
        "/api/v1/reports/planned-vs-actual",
        headers=headers,
        params={"period": "2026-10", "process_id": str(ctx["proc_pack"].id)},
    )
    assert resp_proc.status_code == 200
    proc_items = resp_proc.json()["items"]
    assert len(proc_items) > 0
    for it in proc_items:
        assert it["process_name"] == "Final Packaging"
        assert it["actual_consumed_qty"] is None
        assert it["actual_status"] == "PROCESS_GRAIN_UNAVAILABLE"


def test_norms_immutability_during_reporting(history_fixture):
    """Asserts that generating historical reports never mutates or updates ConsumptionNorm."""
    client, db, headers, ctx = history_fixture

    norms_before = db.scalars(select(ConsumptionNorm)).all()
    before_count = len(norms_before)
    before_version = norms_before[0].version
    before_params = dict(norms_before[0].parameters)

    # Call report endpoint
    resp = client.get(
        "/api/v1/reports/planned-vs-actual",
        headers=headers,
        params={"period": "2026-10"},
    )
    assert resp.status_code == 200

    # Verify norms unchanged
    norms_after = db.scalars(select(ConsumptionNorm)).all()
    assert len(norms_after) == before_count
    assert norms_after[0].version == before_version
    assert norms_after[0].parameters == before_params
