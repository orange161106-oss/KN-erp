import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import Settings, load_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.db.session import create_db_engine, create_session_factory
from app.security.passwords import PasswordService


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        configuration = settings or load_settings()
        configuration.signing_key()
        configure_logging(configuration.log_level)
        engine = create_db_engine(configuration)
        application.title = configuration.app_name
        application.state.settings = configuration
        application.state.engine = engine
        application.state.session_factory = create_session_factory(engine)
        application.state.passwords = PasswordService()
        logger = logging.getLogger("kn.backend.lifecycle")
        logger.info("application_started")
        try:
            yield
        finally:
            engine.dispose()
            logger.info("application_stopped")

    application = FastAPI(title="KN Consumable ERP", version="0.1.0", lifespan=lifespan)
    register_error_handlers(application)
    application.include_router(api_router)
    return application


app = create_app()
