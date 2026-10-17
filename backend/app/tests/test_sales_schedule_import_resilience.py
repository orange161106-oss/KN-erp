import io
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4
import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.errors import ApplicationError
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.models.auth import Permission, Role, User
from app.models.mappings import ProductPlant
from app.models.masters import Customer, CustomerAlias, Product
from app.models.prd import ImportBatch, PlanningVersion, PRDOrderHeader, PRDOrderItem, PRDRecord
from app.models.production import Plant, Route, RouteStep, Process
from app.security.passwords import PasswordService
from app.security.tokens import create_access_token
from app.services.prd_workspace import preview_sales_schedule_upload, confirm_sales_schedule_import

ALL_PERMISSIONS = [
    'prd.plan.read',
    'prd.plan.create',
    'prd.plan.update',
    'prd.plan.delete',
    'prd.plan.import',
    'prd.plan.export',
    'inventory.stock.read',
]


def create_sample_workbook(part_no="501352VE2B", item_id="LSR030000QQ", qty=100) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales Schedule"

    # 4-tier header
    ws.append(["", "", "", "", "Oct'26"])
    ws.append(["", "", "", "", "22.09.2026"])
    ws.append(["", "", "", "", "01.10.2026"])
    ws.append(["S. No.", "Part No.", "Item ID", "Part Description", "R0"])

    # First block (Ashok Leyland) without explicit header banner
    ws.append(["1", part_no, item_id, "Reinf - Side MBR INR CTR LH", qty])
    ws.append(["", "", "", "ASHOK LEYLAND - TOTAL", qty])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def sales_schedule_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def configure(connection, record):
        connection.create_function("btrim", 1, lambda value: value.strip())
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)

    passwords = PasswordService()
    with Session(engine, expire_on_commit=False) as session:
        grants = [Permission(code=p, description='Workspace test grant') for p in ALL_PERMISSIONS]
        role = Role(code="ADMIN", name="Administrator", permissions=grants)
        user = User(
            username="admin_operator",
            password_hash=passwords.hash("password"),
            roles=[role],
            prd_planning_read=True,
            prd_planning_create=True,
            prd_planning_update=True,
            prd_planning_delete=True,
        )
        session.add_all([role, user] + grants)

        plant1 = Plant(id=uuid4(), name="Plant 1", location="Site 1", is_active=True)
        plant2 = Plant(id=uuid4(), name="Plant 2", location="Site 2", is_active=True)
        session.add_all([plant1, plant2])

        route1 = Route(id=uuid4(), name="Standard Route", is_active=True)
        session.add(route1)

        customer = Customer(id=uuid4(), code="CUST-AL", name="Ashok Leyland", is_active=True)
        session.add(customer)
        session.flush()

        alias = CustomerAlias(
            id=uuid4(),
            customer_id=customer.id,
            alias_text="ASHOK LEYLAND",
            normalized_alias="ashok leyland",
            is_active=True,
        )
        session.add(alias)
        session.commit()

    yield engine


def test_product_reuse_without_duplicate_key_error(sales_schedule_db):
    """Verify that an existing product with (part_number, item_id) is reused and not duplicated."""
    with Session(sales_schedule_db) as session:
        plant1 = session.scalar(select(Plant).where(Plant.name == "Plant 1"))
        route1 = session.scalar(select(Route).where(Route.name == "Standard Route"))
        user = session.scalar(select(User).where(User.username == "admin_operator"))

        # Pre-seed product with (part_number, item_id)
        prod = Product(
            id=uuid4(),
            code="501352VE2B_LSR030000QQ",
            name="Reinf - Side MBR INR CTR LH",
            uom="PCS",
            part_number="501352VE2B",
            item_id="LSR030000QQ",
            is_active=True,
        )
        session.add(prod)
        session.flush()

        # Map route to this product in Plant 1
        pp = ProductPlant(
            product_id=prod.id,
            plant_id=plant1.id,
            route_id=route1.id,
            is_active=True,
            is_primary=True,
        )
        session.add(pp)
        session.commit()

        excel_bytes = create_sample_workbook("501352VE2B", "LSR030000QQ", 75)

        preview = preview_sales_schedule_upload(
            session=session,
            file_bytes=excel_bytes,
            filename="sales_schedule.xlsx",
        )
        assert preview.can_confirm is True
        assert preview.total_part_rows == 1

        confirm_res = confirm_sales_schedule_import(
            session=session,
            file_token=preview.file_token,
            sheet_name="Sales Schedule",
            target_period="2026-10",
            revision_label="R0",
            plant_code="Plant 1",
            actor=user.id,
        )

        assert confirm_res.imported_count == 1
        # Check that existing product was reused, not duplicated
        products = session.scalars(select(Product).where(Product.part_number == "501352VE2B")).all()
        assert len(products) == 1
        assert products[0].id == prod.id

        # Check PRDRecord in dedicated table
        records = session.scalars(select(PRDRecord).where(PRDRecord.target_period == "2026-10")).all()
        assert len(records) == 1
        assert records[0].planned_quantity == Decimal("75.0000")
        assert records[0].product_code == prod.code


def test_missing_route_rejects_with_actionable_error_and_rolls_back(sales_schedule_db):
    """When a product has no route assigned, import must reject with ROUTE_REQUIRED and rollback atomically."""
    with Session(sales_schedule_db) as session:
        user = session.scalar(select(User).where(User.username == "admin_operator"))

        # Pre-seed product with NO route assigned
        prod = Product(
            id=uuid4(),
            code="UNMAPPED_PART",
            name="Unmapped Part Without Route",
            uom="PCS",
            part_number="UNMAPPED_PART_NO",
            item_id="UNMAPPED_ITEM_ID",
            is_active=True,
        )
        session.add(prod)
        session.commit()

        excel_bytes = create_sample_workbook("UNMAPPED_PART_NO", "UNMAPPED_ITEM_ID", 50)

        preview = preview_sales_schedule_upload(
            session=session,
            file_bytes=excel_bytes,
            filename="sales_schedule.xlsx",
        )

        # Preview surfaces warning about missing route
        assert any("no production route assigned" in w for w in preview.warnings)

        # Confirm must raise ROUTE_REQUIRED
        with pytest.raises(ApplicationError) as exc_info:
            confirm_sales_schedule_import(
                session=session,
                file_token=preview.file_token,
                sheet_name="Sales Schedule",
                target_period="2026-10",
                revision_label="R0",
                plant_code="Plant 1",
                actor=user.id,
            )

        assert exc_info.value.code == "ROUTE_REQUIRED"
        assert exc_info.value.status_code == 422
        assert "has no production route assigned" in exc_info.value.message

        # Verify atomic rollback: no PRDRecord or PlanningVersion persisted
        prd_count = session.scalar(select(PRDRecord))
        assert prd_count is None
        version_count = session.scalar(select(PlanningVersion))
        assert version_count is None


def test_deterministic_route_resolution_from_another_plant(sales_schedule_db):
    """If a product has an active route in Plant 2, it is deterministically resolved for Plant 1."""
    with Session(sales_schedule_db) as session:
        plant2 = session.scalar(select(Plant).where(Plant.name == "Plant 2"))
        route1 = session.scalar(select(Route).where(Route.name == "Standard Route"))
        user = session.scalar(select(User).where(User.username == "admin_operator"))

        prod = Product(
            id=uuid4(),
            code="MULTI_PLANT_PART",
            name="Part with Route in Plant 2",
            uom="PCS",
            part_number="PART_MULTI",
            item_id="ITEM_MULTI",
            is_active=True,
        )
        session.add(prod)
        session.flush()

        # Map route in Plant 2
        pp2 = ProductPlant(
            product_id=prod.id,
            plant_id=plant2.id,
            route_id=route1.id,
            is_active=True,
            is_primary=True,
        )
        session.add(pp2)
        session.commit()

        excel_bytes = create_sample_workbook("PART_MULTI", "ITEM_MULTI", 120)

        preview = preview_sales_schedule_upload(
            session=session,
            file_bytes=excel_bytes,
            filename="sales_schedule.xlsx",
        )

        confirm_res = confirm_sales_schedule_import(
            session=session,
            file_token=preview.file_token,
            sheet_name="Sales Schedule",
            target_period="2026-10",
            revision_label="R0",
            plant_code="Plant 1",
            actor=user.id,
        )

        assert confirm_res.imported_count == 1

        # ProductPlant for Plant 1 was created with route1.id
        plant1 = session.scalar(select(Plant).where(Plant.name == "Plant 1"))
        pp1 = session.scalar(
            select(ProductPlant).where(
                ProductPlant.product_id == prod.id,
                ProductPlant.plant_id == plant1.id,
            )
        )
        assert pp1 is not None
        assert pp1.route_id == route1.id
