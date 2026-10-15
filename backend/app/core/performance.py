"""Log slow requests without URLs, request bodies, SQL or employee information."""
import logging
from time import perf_counter

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("kn.backend.performance")


class SlowRequestMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        started, status = perf_counter(), 500
        async def capture(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)
        try:
            await self.app(scope, receive, capture)
        finally:
            elapsed_ms = round((perf_counter() - started) * 1000)
            settings = getattr(scope["app"].state, "settings", None)
            threshold = getattr(settings, "http_slow_request_ms", 1000)
            if elapsed_ms >= threshold:
                # Log the registered template (/users/{id}), not the actual URL.
                template = getattr(scope.get("route"), "path", "unmatched")
                logger.warning("slow_request method=%s route=%s status=%s elapsed_ms=%s",
                               scope.get("method"), template, status, elapsed_ms)
