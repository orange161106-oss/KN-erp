"""Bounded reconnects must not retry schema/credential errors or expose secrets."""
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.errors import ApplicationError
from app.services.auth import _read_authentication
from app.tests.test_permission_foundation import db


def failure(kind=OperationalError, state=None):
    original = Exception('secret connection URL and password must never be logged')
    original.sqlstate = state
    return kind('private SQL', {}, original)


@pytest.mark.parametrize('state', [None, '08006'])
def test_transient_failure_releases_transaction_and_retries_once(state):
    session = Mock()
    expected = object()
    operation = Mock(side_effect=[failure(state=state), expected])
    assert _read_authentication(session, operation) is expected
    assert operation.call_count == 2
    session.rollback.assert_called_once()


def test_repeated_failure_returns_503_without_secrets(caplog):
    session = Mock()
    operation = Mock(side_effect=failure())
    with pytest.raises(ApplicationError) as error:
        _read_authentication(session, operation)
    assert error.value.status_code == 503
    assert operation.call_count == 2
    session.rollback.assert_called_once()
    assert 'category=connection' in caplog.text
    assert 'password' not in caplog.text
    assert 'private SQL' not in caplog.text


@pytest.mark.parametrize('kind,state', [(ProgrammingError, '42703'), (OperationalError, '28P01'),
                                       (OperationalError, '53300')])
def test_permanent_or_capacity_failures_are_not_retried(kind, state):
    session = Mock()
    operation = Mock(side_effect=failure(kind, state))
    with pytest.raises(ApplicationError):
        _read_authentication(session, operation)
    operation.assert_called_once()
    session.rollback.assert_not_called()


def test_rollback_failure_stops_recovery():
    session = Mock()
    session.rollback.side_effect = failure()
    operation = Mock(side_effect=failure())
    with pytest.raises(ApplicationError):
        _read_authentication(session, operation)
    operation.assert_called_once()


def test_login_recovers_before_returning_token_and_current_identity(db, monkeypatch):
    from app.core.config import Settings
    from app.models.auth import User
    from app.schemas.auth import LoginRequest
    from app.services import auth
    user = User(username='recovery_operator', password_hash='synthetic-hash', is_active=True)
    db.add(user); db.commit()
    identity = user.id
    original = auth.find_user_by_username
    attempts = []
    def interrupted_lookup(session, username):
        attempts.append(username)
        if len(attempts) == 1:
            raise failure()
        return original(session, username)
    monkeypatch.setattr(auth, 'find_user_by_username', interrupted_lookup)
    settings = Settings(_env_file=None, database_url='postgresql://operator@localhost/test',
                        auth_secret_key='synthetic-signing-key-at-least-32-bytes')
    passwords = Mock(); passwords.verify.return_value = True
    result = auth.login(db, LoginRequest(username='recovery_operator', password='synthetic-password'), settings, passwords)
    assert result.access_token
    assert result.user.id == identity
    assert result.user.username == 'recovery_operator'
    assert len(attempts) == 2
    passwords.verify.assert_called_once()


def test_recovery_does_not_turn_invalid_credentials_into_success(monkeypatch):
    from app.schemas.auth import LoginRequest
    from app.services import auth
    lookup = Mock(side_effect=[failure(), None])
    monkeypatch.setattr(auth, 'find_user_by_username', lookup)
    passwords = Mock()
    with pytest.raises(ApplicationError) as error:
        auth.login(Mock(), LoginRequest(username='unknown', password='synthetic'), Mock(), passwords)
    assert error.value.code == 'INVALID_CREDENTIALS'
    assert error.value.status_code == 401
    passwords.verify_dummy.assert_called_once()
