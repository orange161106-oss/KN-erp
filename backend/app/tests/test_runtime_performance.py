"""Query budgets, worker concurrency and safe failure recovery without a live DB."""
import asyncio
import inspect
import io
from decimal import Decimal
from threading import Event
from unittest.mock import Mock, patch
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError, TimeoutError
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.errors import register_error_handlers
from app.db.reliability import database_unavailable
from app.db.session import create_db_engine, warm_remote_connection
from app.models.audit import AuditLog
from app.models.inventory_masters import Consumable, Unit
from app.models.stock_statements import StockStatementLine, StockParameter
from app.schemas.stock_statements import StockStatementBatchUpdateRequest, StockParameterBatchUpdateRequest
from app.services import stock_statement_service as statements, stock_management_service as parameters
from app.tests.test_loading_performance import queries
from app.tests.test_stock_statement_delete import db, identity, seed as statement_seed
from app.tests.test_stock_management_delete import seed as parameter_seed


@pytest.mark.parametrize("module", ["statement", "management"])
def test_500_row_patch_has_constant_read_budget_and_preserves_every_audit(db, module):
    batch = statement_seed(db) if module == "statement" else parameter_seed(db)
    actor = identity(db, inventory_update=True)
    model = StockStatementLine if module == "statement" else StockParameter
    field = "receipt_qty" if module == "statement" else "min_stock_level"
    db.add_all([model(batch_id=batch.id, item_id=f"PERF-{n}", source_row=n) for n in range(3, 501)])
    batch.row_count = 500
    db.commit()
    ids = list(db.scalars(select(model.id).where(model.batch_id == batch.id)))
    batch_id = batch.id
    db.expunge_all()
    payload_type = StockStatementBatchUpdateRequest if module == "statement" else StockParameterBatchUpdateRequest
    payload = payload_type(month=9, year=2026, batch_id=batch_id,
                           updates=[{"id": row_id, field: "12.1234"} for row_id in ids])
    with queries(db) as executed:
        if module == "statement":
            result = statements.batch_update_stock_statement(db, payload=payload, user=actor)
        else:
            result = parameters.batch_update_stock_parameters(db, payload, actor)
    reads = [sql for sql in executed if sql.lstrip().upper().startswith("SELECT")]
    assert len(reads) <= 5  # Locked batch, edited rows and bounded response reads.
    assert len(result.records) == 500
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 500
    assert all(value == Decimal("12.1234") for value in db.scalars(select(getattr(model, field))))


def test_filtered_statement_preserves_whole_batch_totals_and_warning_semantics_in_three_reads(db):
    batch = statement_seed(db)
    rows = list(db.scalars(select(StockStatementLine).where(StockStatementLine.batch_id == batch.id)))
    rows[0].opening_value = Decimal("0.1234")
    rows[0].warning_codes = ["RECONCILIATION"]
    rows[1].opening_value = Decimal("2.4321")
    rows[1].item_class = "PRODUCT_OR_OTHER"
    unit = Unit(code='PCS',name='Pieces');db.add(unit);db.flush()
    db.add(Consumable(code=rows[0].item_id,item_id=rows[0].item_id,name='Synthetic consumable',unit_id=unit.id))
    db.commit()
    db.expunge_all()
    with queries(db) as executed:
        result = statements.get_stock_statement(db, 9, 2026, item_class_filter='ALL',has_warnings_only=True)
    assert len(executed) == 3
    assert len(result.records) == 1
    assert result.summary.item_count == 2
    assert result.summary.total_opening_value == Decimal("2.5555")
    assert result.summary.consumable_count == 1
    assert result.summary.product_or_other_count == 1
    assert result.summary.warning_rows_count == 1
    assert result.metadata.created_by_name == "delete_operator"


def test_parameter_search_keeps_summary_over_entire_batch(db):
    batch = parameter_seed(db)
    rows = list(db.scalars(select(StockParameter).where(StockParameter.batch_id == batch.id)))
    rows[0].lead_time_days = None
    rows[1].min_stock_level = 30
    db.commit()
    db.expunge_all()
    with queries(db) as executed:
        result = parameters.get_stock_management(db, 9, 2026, search="TEST-1")
    assert len(executed) == 2
    assert len(result.records) == 1
    assert result.summary.item_count == 2
    assert result.summary.missing_limits_count == 1
    assert result.summary.min_exceeds_max_count == 1


def test_pool_budget_is_bounded_and_operator_configurable():
    settings = Settings(_env_file=None, database_url="postgresql://operator@localhost/test")
    with patch("app.db.session.create_engine") as create:
        create_db_engine(settings)
    options = create.call_args.kwargs
    assert options["pool_size"] == 5 and options["max_overflow"] == 5
    assert options["pool_pre_ping"] and options["pool_use_lifo"]
    assert options["pool_recycle"] == 1800 and options["pool_timeout"] == 10
    with patch("app.db.session.create_engine") as create:
        create_db_engine(settings.model_copy(update={"db_pool_size": 2, "db_max_overflow": 0}))
    assert create.call_args.kwargs["pool_size"] == 2
    assert create.call_args.kwargs["max_overflow"] == 0


@pytest.mark.parametrize('port,mode,transaction', [
    (5432,'auto',False), (6543,'auto',True), (6432,'transaction',True),
    (6543,'session',False), (5432,'transaction',True),
])
def test_pooler_mode_distinguishes_shared_host_ports_and_explicit_override(port,mode,transaction):
    settings = Settings(_env_file=None, database_url=f'postgresql://operator@synthetic.pooler.supabase.com:{port}/test',
        db_pool_mode=mode,db_pool_size=2,db_max_overflow=0,db_pool_timeout_seconds=7,db_pool_recycle_seconds=900)
    with patch('app.db.session.create_engine') as create:
        create_db_engine(settings)
    options=create.call_args.kwargs
    assert options['connect_args']['prepare_threshold'] is None
    if transaction:
        assert options['poolclass'] is NullPool and 'pool_size' not in options
    else:
        assert options['pool_size']==2 and options['max_overflow']==0
        assert options['pool_pre_ping'] and options['pool_use_lifo']
        assert options['pool_timeout']==7 and options['pool_recycle']==900


def test_remote_startup_warms_only_one_read_connection_and_tolerates_outage(caplog):
    from unittest.mock import MagicMock
    settings = Settings(_env_file=None, database_url="postgresql://operator@remote.example/test")
    engine = MagicMock()
    warm_remote_connection(engine, settings)
    engine.connect.return_value.__enter__.return_value.exec_driver_sql.assert_called_once_with("SELECT 1")
    engine.reset_mock()
    engine.connect.side_effect = OperationalError("private SQL", {}, Exception("private password"))
    warm_remote_connection(engine, settings)
    assert "category=connection" in caplog.text and "private" not in caplog.text
    engine.reset_mock()
    warm_remote_connection(engine, settings.model_copy(update={"db_warmup_on_startup": False}))
    engine.connect.assert_not_called()
    warm_remote_connection(engine, settings.model_copy(update={"app_env": "test"}))
    engine.connect.assert_not_called()


@pytest.mark.parametrize("kind,state,category", [
    (OperationalError, "08006", "connection"), (ProgrammingError, "42703", "schema"),
    (OperationalError, "28P01", "credentials"), (OperationalError, "53300", "capacity"),
])
def test_failure_handler_exposes_safe_diagnostic_and_only_transient_read_retry(kind, state, category, caplog):
    original = Exception("private password and SQL")
    original.sqlstate = state
    error = database_unavailable(kind("private SQL", {}, original))
    assert error.status_code == 503
    assert error.details == {"category": category, "retryable": category == "connection"}
    assert "private" not in caplog.text and "password" not in caplog.text


def test_exhausted_local_pool_is_capacity_not_a_retry_storm():
    assert database_unavailable(TimeoutError("private pool error")).details == {
        "category": "capacity", "retryable": False,
    }


@pytest.mark.parametrize("method,retryable", [("GET", True), ("POST", False), ("PATCH", False), ("DELETE", False)])
def test_database_exception_response_never_invites_retrying_a_write(method, retryable):
    from fastapi.testclient import TestClient
    application = FastAPI()
    register_error_handlers(application)
    @application.api_route("/probe", methods=[method])
    def probe():
        raise OperationalError("private SQL", {}, Exception("private password"))
    with TestClient(application) as client:
        response = client.request(method, "/probe")
    assert response.status_code == 503
    assert response.json()["details"] == {"category": "connection", "retryable": retryable}
    assert "private" not in response.text


def test_large_stock_response_is_compressed_without_changing_decimal_values(db):
    from app.tests.test_stock_statement_delete import client_for
    batch = statement_seed(db)
    db.add_all([StockStatementLine(batch_id=batch.id, item_id=f"PERF-{n}", source_row=n,
                                  closing_qty=Decimal("12.1234")) for n in range(3, 50)])
    db.commit()
    with client_for(db, identity(db, inventory_read=True)) as client:
        response = client.get("/api/v1/inventory/statement?month=9&year=2026&item_class=ALL")
    assert response.status_code == 200
    assert response.headers["content-encoding"] == "gzip"
    assert response.json()["records"][-1]["closing_qty"] == "12.1234"


def test_slow_request_logging_uses_route_template_not_private_query_or_path(caplog):
    from fastapi.testclient import TestClient
    from app.core.performance import SlowRequestMiddleware
    from types import SimpleNamespace
    application = FastAPI()
    application.state.settings = SimpleNamespace(http_slow_request_ms=1)
    application.add_middleware(SlowRequestMiddleware)
    @application.get("/probe/{identity}")
    async def probe(identity: str):
        await asyncio.sleep(0.005)
        return {"ok": True}
    with TestClient(application) as client:
        assert client.get("/probe/private-identifier?password=private-password").status_code == 200
    assert "route=/probe/{identity}" in caplog.text
    assert "private" not in caplog.text


def test_excel_preview_does_not_block_an_unrelated_request():
    from app.modules.masters.router import router
    from app.security.dependencies import get_current_user
    from app.schemas.auth import CurrentUser
    from app.schemas.masters import ProductSourcePreview
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_current_user] = lambda: CurrentUser(
        id=uuid4(), username="synthetic_operator", roles=[], permissions=[], is_super_admin=True)
    started, released = Event(), Event()
    def slow_preview(*args):
        started.set()
        assert released.wait(3), "The request worker blocked other endpoints"
        return ProductSourcePreview.model_construct()
    @application.get("/probe")
    async def probe():
        released.set()
        return {"ok": True}
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test") as client:
            upload = asyncio.create_task(client.post("/masters/products/preview", files={"file": ("synthetic.xlsx", b"unused")}))
            try:
                for _ in range(100):
                    if started.is_set():
                        break
                    await asyncio.sleep(0.01)
                assert started.is_set()
                result = await asyncio.wait_for(client.get("/probe"), timeout=1)
                assert result.json() == {"ok": True}
                await upload
            finally:
                released.set()
                if not upload.done():
                    await upload
    with patch("app.modules.masters.router.product_source.preview", side_effect=slow_preview):
        asyncio.run(scenario())
