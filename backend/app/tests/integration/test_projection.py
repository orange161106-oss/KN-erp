from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.errors import ApplicationError
from app.db.session import create_session_factory
from app.models.audit import AuditLog
from app.models.inventory import StockSnapshot
from app.models.plant_workflow import RequirementAdjustment
from app.models.projection import ProjectionInputSet
from app.schemas.projection import ProjectionInputs
from app.services.projection import import_inputs
from app.tests.integration.test_inventory import postgres_inventory
from app.tests.test_inventory import source_payload
from app.tests.test_projection import BASE, D, at, input_payload, seed_requirement, view

pytestmark = pytest.mark.integration


@pytest.fixture
def postgres_projection(postgres_inventory):
    engine, client, headers, ids = postgres_inventory
    client.app.state.settings.projection_import_enabled = True
    # Exercise the actual repeatable-read dependency against the isolated schema.
    client.app.state.session_factory = create_session_factory(engine)
    with Session(engine, expire_on_commit=False) as session:
        plant_id, version_id, adjustment_id = seed_requirement(session, ids['actor_id'], ids['material_id'], 'KG')
    stock = source_payload(ids['material_id'], ids['unit_id'], as_of=at(2).isoformat(), quantity='100')
    assert client.post('/api/v1/inventory/imports', headers=headers, json=stock).status_code == 201
    with Session(engine) as session:
        snapshot_id = session.scalar(select(StockSnapshot.id))
    data = input_payload(ids['material_id'], ids['unit_id'], plant_id, version_id, snapshot_id)
    return engine, client, headers, ids, data, adjustment_id


def test_postgres_api_exact_projection_and_input_evidence(postgres_projection):
    engine, client, headers, ids, data, _ = postgres_projection
    response = client.post(BASE + '/inputs', headers=headers, json=data)
    assert response.status_code == 201, response.text
    assert response.json()['imported_at'].endswith('Z')
    result = view(client, headers, data)
    assert result.status_code == 200, result.text
    assert result.json()['projected_stock'] == '40.0000'
    assert result.json()['inputs']['msl_history'][0]['approval_reference'] == 'synthetic-msl-approval'
    with Session(engine) as session:
        record = session.scalar(select(ProjectionInputSet))
        assert record.requirement_manifest['adjustments'][0]['quantity'] == '80.0000'


@pytest.mark.parametrize('operation', ['UPDATE projection_input_sets SET id=id', 'DELETE FROM projection_input_sets'])
def test_postgres_projection_history_cannot_be_overwritten(postgres_projection, operation):
    engine, client, headers, ids, data, _ = postgres_projection
    assert client.post(BASE + '/inputs', headers=headers, json=data).status_code == 201
    with pytest.raises(DBAPIError) as error:
        with engine.begin() as connection:
            connection.execute(text(operation))
    assert error.value.orig.sqlstate == '55000'


def test_postgres_report_does_not_mix_concurrent_requirement_versions(postgres_projection, monkeypatch):
    engine, client, headers, ids, data, adjustment_id = postgres_projection
    assert client.post(BASE + '/inputs', headers=headers, json=data).status_code == 201
    from app.services import projection
    original = projection.get_final_requirements
    def concurrently_changed(session, **filters):
        result = original(session, **filters)
        assert session.execute(text('SHOW transaction_isolation')).scalar_one() == 'repeatable read'
        with Session(engine) as writer:
            writer.get(RequirementAdjustment, adjustment_id).requested_qty = D('90')
            writer.commit()
        return result
    monkeypatch.setattr(projection, 'get_final_requirements', concurrently_changed)
    response = view(client, headers, data)
    assert response.status_code == 200 and response.json()['projected_stock'] == '40.0000'
    monkeypatch.setattr(projection, 'get_final_requirements', original)
    response = view(client, headers, data).json()
    assert response['projected_stock'] is None
    assert 'REQUIREMENT_INPUTS_CHANGED' in {row['code'] for row in response['limitations']}


def test_concurrent_input_import_has_one_evidence_row_and_one_audit(postgres_projection):
    engine, client, headers, ids, data, _ = postgres_projection
    barrier = Barrier(2)
    def worker():
        with Session(engine, expire_on_commit=False) as session:
            barrier.wait(timeout=10)
            try:
                result = import_inputs(session, ProjectionInputs.model_validate(data), ids['actor_id'], enabled=True)
                return 'REPLAY' if result.replayed else 'CREATED'
            except ApplicationError as error:
                return error.code
    with ThreadPoolExecutor(max_workers=2) as workers:
        outcomes = [item.result(timeout=20) for item in [workers.submit(worker), workers.submit(worker)]]
    assert outcomes.count('CREATED') == 1
    assert set(outcomes) <= {'CREATED', 'REPLAY', 'PROJECTION_SOURCE_CONFLICT'}
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ProjectionInputSet)) == 1
        assert session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == 'IMPORT_PROJECTION_INPUTS')) == 1
    assert client.post(BASE + '/inputs', headers=headers, json=data).json()['replayed'] is True
