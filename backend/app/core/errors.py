import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.schemas.error import ErrorResponse

logger = logging.getLogger("kn.backend.errors")


class ApplicationError(Exception):
    def __init__(
        self, code: str, message: str, status_code: int,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.headers = headers


def error_response(
    status: int, code: str, message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(code=code, message=message, details=details or {})
    return JSONResponse(status_code=status, content=body.model_dump(), headers=headers)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def application_error_handler(request: Request, exc: ApplicationError):
        return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        # Omit input and validator context, which may contain credentials or payloads.
        errors = [{"location": list(e["loc"]), "type": e["type"]} for e in exc.errors()]
        return error_response(422, "VALIDATION_ERROR", "Request validation failed.", {"errors": errors})

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "HTTP request failed."
        return error_response(exc.status_code, "HTTP_ERROR", message, headers=exc.headers)

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        logger.error("unhandled_exception type=%s", type(exc).__name__)
        return error_response(500, "INTERNAL_SERVER_ERROR", "An unexpected error occurred.")
