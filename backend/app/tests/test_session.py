from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db, session_scope
from app.main import create_app


def test_session_does_not_commit_implicitly():
    session = MagicMock(spec=Session)
    session.__enter__.return_value = session
    with session_scope(lambda: session) as active:
        assert active is session
    session.commit.assert_not_called()
    session.__exit__.assert_called_once()


def test_exception_rolls_back_and_closes_session():
    session = MagicMock(spec=Session)
    session.__enter__.return_value = session
    with pytest.raises(RuntimeError):
        with session_scope(lambda: session):
            raise RuntimeError("failed service")
    session.rollback.assert_called_once()
    session.__exit__.assert_called_once()


def test_lifespan_disposes_engine(settings, monkeypatch):
    engine = MagicMock()
    monkeypatch.setattr("app.main.create_db_engine", lambda _: engine)
    application = create_app(settings)
    application.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
    with TestClient(application):
        engine.dispose.assert_not_called()
    engine.dispose.assert_called_once()
