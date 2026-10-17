"""Faster screen reads preserve existing quantities, selection, and access boundaries."""
import inspect
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.core.errors import ApplicationError, register_error_handlers
from app.db.session import get_db
from app.models.prd import PlanningVersion
from app.schemas.requirements import CalculationRunRequest
from app.schemas.requirement_loading import CentralWorkspace, MonthlyWorkspace
from app.security.dependencies import get_current_user
from app.services import basic_planning as basic, requirements_workspace as monthly
from app.services.requirements import get_calculated_requirements, get_calculation_errors
from app.services.plant_workflow import get_final_requirements
from app.tests.test_central_basic_planning import db, catalog, imported, WHEN
from app.tests.test_loading_performance import queries
from app.tests.test_permission_foundation import actor


def test_central_revision_list_uses_one_query_and_keeps_noncentral_latest_semantics(db,catalog):
    identity,_,_=imported(db,catalog)
    current=db.get(PlanningVersion,identity)
    db.add(PlanningVersion(planning_period=current.planning_period,version_number=current.version_number+1,
        source_filename='synthetic-manual.xlsx',created_by=catalog[0].id))
    db.commit();db.expunge_all()
    with queries(db) as statements:
        versions=basic.versions(db)
    assert len(statements)==1 and len(versions)==1
    assert versions[0]['id']==identity and versions[0]['is_latest'] is False


def test_combined_central_view_matches_existing_reads_and_is_read_only(db,catalog):
    identity,_,_=imported(db,catalog)
    basic.calculate(db,CalculationRunRequest(planning_version_id=identity,as_of_date=WHEN),catalog[0].id)
    expected={'calculations':get_calculated_requirements(db,identity),
        'errors':get_calculation_errors(db,identity),'summary':get_final_requirements(db,planning_version_id=identity)}
    with queries(db) as statements:
        view=CentralWorkspace.model_validate(basic.workspace(db))
    assert view.selected_version_id==identity
    assert view.results.model_dump()==view.results.model_validate(expected).model_dump()
    assert all(statement.lstrip().upper().startswith('SELECT') for statement in statements)
    with pytest.raises(ApplicationError) as failure:
        basic.workspace(db,uuid4())
    assert failure.value.code=='CENTRAL_VERSION_REQUIRED'


def test_empty_workspace_does_not_invent_a_plan(db):
    value=CentralWorkspace.model_validate(basic.workspace(db))
    assert value.versions==[] and value.results is None and value.selected_version_id is None


def test_combined_monthly_view_keeps_metadata_filters_and_quantities(db,catalog):
    identity,_,_=imported(db,catalog)
    basic.calculate(db,CalculationRunRequest(planning_version_id=identity,as_of_date=WHEN),catalog[0].id)
    value=MonthlyWorkspace.model_validate(monthly.load_workspace_view(db,10,2026,search='PART-A'))
    assert value.plan_metadata.record_count==2
    assert len(value.records)==1 and value.records[0].part_number=='PART-A'
    assert value.records[0].required_qty=='200.0000'


def test_combined_workspace_routes_keep_permission_and_central_plant_boundaries(db,catalog):
    from app.modules.requirements.basic_router import router as central_router
    from app.modules.requirements.requirements_workspace_router import router as monthly_router
    imported(db,catalog)
    user=actor(requirements_read=True,plant_ids=[uuid4()])
    app=FastAPI();register_error_handlers(app)
    app.include_router(central_router,prefix='/api/v1');app.include_router(monthly_router,prefix='/api/v1')
    app.dependency_overrides[get_db]=lambda:db
    app.dependency_overrides[get_current_user]=lambda:user
    with TestClient(app) as client:
        for path in ('/api/v1/requirements/basic/workspace','/api/v1/requirements/workspace/view?month=10&year=2026'):
            assert client.get(path).status_code==403
        user=actor(is_super_admin=True)
        central=client.get('/api/v1/requirements/basic/workspace')
        assert central.status_code==200 and len(central.json()['versions'])==1
        assert client.get('/api/v1/requirements/workspace/view?month=10&year=2026').status_code==200
        user=actor()
        assert client.get('/api/v1/requirements/basic/workspace').status_code==403


def test_blocking_excel_handlers_use_request_workers():
    from app.modules.rules.router import preview_norm_import,confirm_norm_import
    from app.modules.masters.product_master_router import preview_assemble_upload
    from app.modules.requirements.router import handle_bulk_upload_items
    for handler in (preview_norm_import,confirm_norm_import,preview_assemble_upload,handle_bulk_upload_items):
        assert not inspect.iscoroutinefunction(handler)
