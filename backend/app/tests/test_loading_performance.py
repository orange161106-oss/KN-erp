"""Bound remote round trips without weakening grants or mapping validation."""
from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import ProgrammingError

from app.tests.test_permission_foundation import db
from app.api.production import get_routes
from app.core.errors import ApplicationError
from app.models.auth import User, Role, Permission
from app.models.inventory_masters import Unit, Consumable
from app.models.masters import Product
from app.models.mappings import ProductPlant, ProductProcessConsumable
from app.models.production import Plant, Route, RouteStep, Process
from app.repositories.auth import find_user_with_permissions
from app.schemas.production import RouteResponse
from app.services.product import list_products
from app.services.mappings import resolve_product_mapping, validate_mappings


@contextmanager
def queries(db):
    statements = []
    def capture(connection, cursor, statement, parameters, context, many):
        statements.append(statement)
    engine = db.get_bind()
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        yield statements
    finally:
        event.remove(engine, 'before_cursor_execute', capture)


def test_account_and_overlapping_role_grants_load_in_one_query_and_refresh(db):
    grant = Permission(code='reports:view', description='Synthetic grant')
    user = User(username='timing_operator', password_hash='unused', roles=[
        Role(code='ROLE1', name='One', permissions=[grant]),
        Role(code='ROLE2', name='Two', permissions=[grant]),
    ])
    db.add(user); db.commit()
    identity = user.id
    db.expunge_all()
    with queries(db) as statements:
        loaded = find_user_with_permissions(db, identity)
        assert {role.code for role in loaded.roles} == {'ROLE1', 'ROLE2'}
        assert {permission.code for role in loaded.roles for permission in role.permissions} == {'reports:view'}
    assert len(statements) == 1
    # Bypass the identity map to prove subsequent reads don't serve stale grants.
    db.execute(text('DELETE FROM user_roles WHERE user_id = :id'), {'id': identity.hex})
    db.execute(text('UPDATE users SET is_active = 0 WHERE id = :id'), {'id': identity.hex})
    db.commit()
    with queries(db) as statements:
        refreshed = find_user_with_permissions(db, identity)
        assert refreshed.roles == []
        assert not refreshed.is_active
    assert len(statements) == 1


def test_product_read_is_one_query_including_external_identifiers(db):
    db.add_all([Product(code='B', name='Second', uom='PCS', item_id='ITEM-B', part_number='PART-B'),
                Product(code='A', name='First', uom='PCS')])
    db.commit(); db.expunge_all()
    with queries(db) as statements:
        products = list_products(db)
        assert [product.code for product in products] == ['A', 'B']
        assert products[1].item_id == 'ITEM-B'
    assert len(statements) == 1


@pytest.mark.parametrize('sqlstate,translated', [('42703', True), ('42P01', True), ('42501', False)])
def test_product_schema_error_remains_actionable_without_masking_other_errors(sqlstate, translated):
    class DatabaseError(Exception):
        pass
    original = DatabaseError('Synthetic database error')
    original.sqlstate = sqlstate
    class BrokenSession:
        def scalars(self, statement):
            raise ProgrammingError('synthetic', {}, original)
    with pytest.raises(ApplicationError if translated else ProgrammingError) as failure:
        list_products(BrokenSession())
    if translated:
        assert failure.value.code == 'PRODUCT_DATABASE_SETUP_REQUIRED'


def test_route_serialization_batches_steps_for_all_routes(db):
    process = Process(id=uuid4(), name='Synthetic process')
    routes = [Route(id=uuid4(), name=f'Route {i}') for i in range(12)]
    db.add_all([process, *routes]); db.flush()
    db.add_all([RouteStep(route_id=route.id, process_id=process.id, sequence_order=1) for route in routes])
    db.commit(); db.expunge_all()
    with queries(db) as statements:
        responses = [RouteResponse.model_validate(route) for route in get_routes(db=db)]
        assert len(responses) == 12
        assert all(len(route.steps) == 1 for route in responses)
    assert len(statements) == 2


def graph(db):
    unit = Unit(id=uuid4(), code='PCS', name='Pieces')
    material = Consumable(id=uuid4(), code='M1', name='Material', unit_id=unit.id, is_active=False)
    plants = [Plant(id=uuid4(), name='Primary plant'), Plant(id=uuid4(), name='Inactive plant', is_active=False)]
    process = Process(id=uuid4(), name='Inactive process', is_active=False)
    empty_process = Process(id=uuid4(), name='Unmapped process')
    route = Route(id=uuid4(), name='Route')
    products = [Product(id=uuid4(), code=f'P{i}', name=f'Product {i}', uom='PCS') for i in range(3)]
    db.add(unit); db.flush()
    db.add_all([material, *plants, process, empty_process, route, *products]); db.flush()
    db.add_all([RouteStep(route_id=route.id, process_id=process.id, sequence_order=2),
                RouteStep(route_id=route.id, process_id=empty_process.id, sequence_order=1)])
    for product in products[:2]:
        for index, plant in enumerate(plants):
            db.add(ProductPlant(product_id=product.id, plant_id=plant.id, route_id=route.id, is_primary=index == 0))
        db.add(ProductProcessConsumable(product_id=product.id, process_id=process.id, consumable_id=material.id))
    db.commit()
    identity, primary_plant = products[0].id, plants[0].id
    db.expunge_all()
    return identity, primary_plant


def test_resolution_batches_multi_plant_steps_consumables_and_units(db):
    identity, primary_plant = graph(db)
    with queries(db) as statements:
        result = resolve_product_mapping(db, identity)
        assert len(result.plant_mappings) == 2
        assert result.plant_mappings[0].is_primary
        for plant in result.plant_mappings:
            assert [step.sequence_order for step in plant.steps] == [1, 2]
            assert plant.steps[0].consumables == []
            assert plant.steps[1].consumables[0].unit == 'PCS'
            assert not plant.steps[1].consumables[0].is_active
    assert len(statements) == 5
    filtered = resolve_product_mapping(db, identity, primary_plant)
    assert [plant.plant_id for plant in filtered.plant_mappings] == [primary_plant]


def test_mapping_audit_batches_products_and_preserves_integrity_issues(db):
    graph(db)
    with queries(db) as statements:
        result = validate_mappings(db)
    assert len(statements) == 4
    assert result.total_products_checked == 3
    assert result.unmapped_products_count == 1
    assert not result.is_valid
    assert sum(issue.issue_type == 'UNMAPPED_PRODUCT' for issue in result.issues) == 1
    assert sum(issue.issue_type == 'PROCESS_WITHOUT_CONSUMABLES' for issue in result.issues) == 4
    assert sum(issue.issue_type == 'INACTIVE_ENTITY' for issue in result.issues) == 10


def test_hundreds_of_unmapped_products_use_two_queries(db):
    db.add_all([Product(code=f'ITEM{i:04}', name='Synthetic product', uom='PCS') for i in range(600)])
    db.commit(); db.expunge_all()
    with queries(db) as statements:
        report = validate_mappings(db)
    assert len(statements) == 2
    assert report.unmapped_products_count == 600
    assert len(report.issues) == 600
