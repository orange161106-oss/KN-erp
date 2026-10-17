import pytest
from app.core.config import Settings
from app.db.session import create_db_engine, create_session_factory, session_scope


@pytest.fixture
def db_session():
    settings = Settings()
    engine = create_db_engine(settings)
    factory = create_session_factory(engine)
    with session_scope(factory) as session:
        yield session

