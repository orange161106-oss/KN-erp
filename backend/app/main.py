import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool
from starlette.middleware.gzip import GZipMiddleware

from app.api.router import api_router
from app.core.config import Settings, load_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.performance import SlowRequestMiddleware
from app.db.session import create_db_engine, create_session_factory, warm_remote_connection
from app.security.passwords import PasswordService
from app.api.production import router as production_router


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
        await run_in_threadpool(warm_remote_connection, engine, configuration)
        logger = logging.getLogger("kn.backend.lifecycle")
        logger.info("application_started")
        try:
            yield
        finally:
            engine.dispose()
            logger.info("application_stopped")

    application = FastAPI(title="KNL Consumable ERP", version="0.1.0", lifespan=lifespan)
    register_error_handlers(application)
    application.add_middleware(GZipMiddleware, minimum_size=2000, compresslevel=4)
    application.add_middleware(SlowRequestMiddleware)
    
    # Existing router
    application.include_router(api_router)
    
    # Attach your new production router here!
    application.include_router(production_router, prefix="/api/v1")
    
    return application


app = create_app()
