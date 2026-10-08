"""Security regression tests use only an isolated SQLite database."""
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from pydantic import ValidationError
from app.core.config import Settings
from app.core.errors import ApplicationError
from app.db.base import Base
from app.db.session import get_db
from app.db.bootstrap_admin import provision
from app.main import create_app
from app.models.auth import User, Role
from app.models.audit import AuditLog
from app.models.production import Plant
from app.schemas.auth import CurrentUser
from app.schemas.user import UserCreate, UserUpdate
from app.security.dependencies import get_current_user
from app.security.permissions import check_permissions
from app.services import users
from app.services.auth import current_user
from app.services.plant_workflow import _assert_plant_access
from app.security.tokens import create_access_token


@pytest.fixture
def db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    @event.listens_for(engine, 'connect')
    def configure(connection, _):
        connection.create_function('btrim', 1, lambda v: v.strip())
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
    engine.dispose()


def actor(**kwargs):
    return CurrentUser(id=uuid4(), username='operator', roles=[], permissions=[], **kwargs)


@pytest.mark.parametrize('code,flag', [
    ('masters.consumables.read', 'can_view_master_data'),
    ('masters.consumables.write', 'can_edit_master_data'),
    ('planning.read', 'can_view_planning'),
    ('requirements.calculate', 'can_run_calculations'),
    ('plant_workflow:confirm', 'can_confirm_demand'),
    ('plant_workflow:approve', 'can_approve_extra_demand'),
    ('purchase.orders.create', 'can_create_po'),
    ('purchase.orders.issue', 'can_approve_po'),
    ('purchase.grns.import', 'can_upload_grn'),
    ('reports.inventory.read', 'can_view_reports'),
])
def test_flags_override_legacy_grants(code, flag):
    denied = actor()
    denied.permissions = [code]
    with pytest.raises(ApplicationError) as exc:
        check_permissions(denied, frozenset({code}))
    assert exc.value.status_code == 403
    check_permissions(actor(**{flag: True}), frozenset({code}))


def test_unmapped_stock_import_not_granted_by_grn_checkbox():
    with pytest.raises(ApplicationError):
        check_permissions(actor(can_upload_grn=True), frozenset({'purchase.grns.import', 'inventory.stock.import'}))


def test_account_service_atomic_audit_and_null_clearing(db):
    root = User(username='root', password_hash='synthetic', is_super_admin=True)
    db.add(root); db.commit()
    identity = actor(is_super_admin=True); identity.id = root.id
    created = users.create_user(db, UserCreate(username='employee', password='synthetic-password',
        employee_id='E001', full_name='Employee', roles=['APPROVER'], is_active=False), identity)
    assert not created.is_active
    updated = users.update_user(db, created.id, UserUpdate(employee_id=None, full_name=None, can_view_reports=True), identity)
    assert updated.employee_id is None and updated.full_name is None
    logs = list(db.scalars(select(AuditLog)))
    assert len(logs) == 2
    assert 'password_hash' not in str([log.new_values for log in logs])
    assert 'synthetic-password' not in str([log.new_values for log in logs])
    assert users.list_users(db, identity)[0].id == created.id
    with pytest.raises(ApplicationError) as exc:
        users.update_user(db, root.id, UserUpdate(is_active=False), identity)
    assert exc.value.code == 'SUPER_ADMIN_IMMUTABLE'
    with pytest.raises(ApplicationError):
        users.list_users(db, CurrentUser(id=created.id, username='employee', roles=['ADMIN'], permissions=['admin:manage']))


def test_duplicate_employee_rolls_back_user_and_audit(db):
    root = User(username='root', password_hash='synthetic', is_super_admin=True)
    db.add(root); db.commit()
    identity = actor(is_super_admin=True); identity.id = root.id
    users.create_user(db, UserCreate(username='one', password='synthetic', employee_id='E1'), identity)
    with pytest.raises(ApplicationError) as exc:
        users.create_user(db, UserCreate(username='two', password='synthetic', employee_id='E1'), identity)
    assert exc.value.status_code == 409
    assert db.scalar(select(User).where(User.username == 'two')) is None
    assert len(list(db.scalars(select(AuditLog)))) == 1


def test_short_update_password_rejected():
    with pytest.raises(ValidationError):
        UserUpdate(password='x')


def test_single_super_admin_constraint(db):
    db.add_all([User(username='root1', password_hash='synthetic', is_super_admin=True),
                User(username='root2', password_hash='synthetic', is_super_admin=True)])
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_bootstrap_is_explicit_and_idempotent(db):
    settings = Settings(_env_file=None, database_url='postgresql://operator@localhost/test',
        super_admin_username='root', super_admin_password='synthetic-password')
    first = provision(db, settings)
    assert provision(db, settings).id == first.id
    assert len(list(db.scalars(select(AuditLog)))) == 1
    assert Settings(_env_file=None, database_url='postgresql://operator@localhost/test').super_admin_password is None


def test_plant_scope_uses_configured_uuid_and_revocation(db):
    plant = Plant(name='Arbitrary plant name')
    user = User(username='employee', password_hash='synthetic', can_access_plant_1=True, can_confirm_demand=True)
    db.add_all([plant, user]); db.commit()
    settings = Settings(_env_file=None, database_url='postgresql://operator@localhost/test',
        auth_secret_key='synthetic-signing-key-at-least-32-bytes', plant_permission_ids={1: plant.id})
    token = create_access_token(user.id, settings)
    identity = current_user(db, token, settings)
    _assert_plant_access(db, identity, plant.id)
    user.can_access_plant_1 = False; db.commit()
    with pytest.raises(ApplicationError):
        _assert_plant_access(db, current_user(db, token, settings), plant.id)


def test_authenticated_user_cannot_bypass_planning_or_master_flags(db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: actor()
    client = TestClient(app)  # no context/lifespan, no operational DB connection
    assert client.get('/api/v1/masters/products').status_code == 403
    assert client.post('/api/v1/prd/workspace/save', json={'records': [], 'deleted_ids': []}).status_code == 403
