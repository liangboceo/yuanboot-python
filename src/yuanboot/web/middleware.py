from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime

from prometheus_client import CollectorRegistry, Counter, Histogram
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse

from yuanboot.logging import request_id_context

logger = logging.getLogger("yuanboot.access")


class HttpMetrics:
    def __init__(self):
        # Each application owns a registry; app factories never share metric state.
        self.registry = CollectorRegistry()
        labels = ("method", "path", "status")
        self.requests = Counter(
            "yuanboot_http_requests_total", "HTTP requests", labels, registry=self.registry
        )
        self.duration = Histogram(
            "yuanboot_http_request_duration_seconds",
            "HTTP duration",
            labels,
            registry=self.registry,
        )


class RequestScopeMiddleware:
    """Pure ASGI middleware: scope survives streaming responses and WebSocket sessions."""

    def __init__(self, app, *, services, metrics):
        self.app = app
        self.services = services
        self.metrics = metrics

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            return await self.app(scope, receive, send)
        request_scope = self.services.create_scope()
        state = scope.setdefault("state", {})
        state["services"] = request_scope
        incoming = Headers(scope=scope).get("x-request-id", "")
        request_id = (
            incoming if re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", incoming) else uuid.uuid4().hex
        )
        state["request_id"] = request_id
        context_token = request_id_context.set(request_id)
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def tracked_send(message):
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["X-Process-Time"] = f"{time.perf_counter() - started:.6f}"
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception:
            logger.exception("Unhandled request error")
            if response_started or scope["type"] != "http":
                raise
            response = JSONResponse(
                {"detail": "Internal Server Error", "request_id": request_id}, status_code=500
            )
            await response(scope, receive, tracked_send)
        finally:
            try:
                await request_scope.aclose()
            finally:
                if scope["type"] == "http":
                    elapsed = time.perf_counter() - started
                    route = scope.get("route")
                    # Unknown paths share one label to avoid unbounded cardinality.
                    path = getattr(route, "path", "__unmatched__")
                    labels = (scope["method"], path, str(status_code))
                    self.metrics.requests.labels(*labels).inc()
                    self.metrics.duration.labels(*labels).observe(elapsed)
                    logger.info(
                        "[yuanboot] %s | %3d | %7d ms| %15s | %5s %s",
                        datetime.now().strftime("%Y/%m/%d - %H:%M:%S.%f")[:-4],
                        status_code,
                        int(elapsed * 1000),
                        Headers(scope=scope).get("host", ""),
                        scope["method"],
                        scope["path"],
                    )
                request_id_context.reset(context_token)
