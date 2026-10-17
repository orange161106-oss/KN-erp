"""Verify bounded batch queries, replay safety and atomic product/audit writes."""
from uuid import uuid4
import pytest
from sqlalchemy import event, func, select
from app.tests.test_permission_foundation import db
from app.models.auth import User
from app.models.audit import AuditLog
from app.models.masters import Product
from app.schemas.masters import ProductBulkCreate
from app.services.product import create_products
from app.core.errors import ApplicationError


def operator(db):
    user = User(id=uuid4(), username='batch_operator', password_hash='unused-test-hash')
    db.add(user)
    db.commit()
    return user.id


def batch(size):
    return ProductBulkCreate(products=[{'code': f'ITEM-{i}', 'name': f'Synthetic product {i}',
        'uom': 'PCS', 'item_id': f'ITEM-{i}', 'part_number': f'PART-{i}'} for i in range(size)],
        source_reference='synthetic-test.xlsx')


def test_593_products_use_one_lookup_and_replay_without_duplicate_audits(db):
    actor = operator(db)
    statements = []
    engine = db.get_bind()
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.upper())
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        created = create_products(db, batch(593), actor)
        assert len(created) == 593
        assert [p.code for p in created] == [p.code for p in batch(593).products]
        assert all(p.created_at is not None for p in created)
        assert len([s for s in statements if s.lstrip().startswith('SELECT') and 'FROM PRODUCTS' in s]) == 1
        assert len([s for s in statements if s.lstrip().startswith('INSERT INTO PRODUCTS')]) == 1
        assert len([s for s in statements if s.lstrip().startswith('INSERT INTO AUDIT_LOGS')]) == 1
        statements.clear()
        replay = create_products(db, batch(593), actor)
        assert [p.id for p in replay] == [p.id for p in created]
        assert not any(s.lstrip().startswith('INSERT') for s in statements)
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 593
    assert set(db.scalars(select(AuditLog.entity_id))) == {p.id for p in created}


def test_conflicting_existing_product_does_not_insert_other_batch_rows(db):
    actor = operator(db)
    create_products(db, batch(1), actor)
    changed = batch(2)
    changed.products[0].name = 'Unapproved replacement description'
    with pytest.raises(ApplicationError) as failure:
        create_products(db, changed, actor)
    assert failure.value.code == 'PRODUCT_SOURCE_CONFLICT'
    assert db.scalar(select(func.count()).select_from(Product)) == 1
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 1


def test_audit_failure_rolls_back_product_batch(db):
    actor = operator(db)
    engine = db.get_bind()
    def fail_audit(connection, cursor, statement, parameters, context, executemany):
        if statement.upper().lstrip().startswith('INSERT INTO AUDIT_LOGS'):
            raise RuntimeError('Synthetic audit insertion failure')
    event.listen(engine, 'before_cursor_execute', fail_audit)
    try:
        with pytest.raises(RuntimeError):
            create_products(db, batch(3), actor)
    finally:
        event.remove(engine, 'before_cursor_execute', fail_audit)
    assert db.scalar(select(func.count()).select_from(Product)) == 0
    assert db.scalar(select(func.count()).select_from(AuditLog)) == 0
