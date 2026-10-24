from __future__ import annotations

import asyncio
from collections.abc import Callable

from fastapi import Request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import JSONResponse, Response

from yuanboot.health import HealthRegistry
from yuanboot.hosting import invoke


def use_health(router, checks: dict[str, Callable] | None = None, *, timeout: float = 2.0):
    checks = dict(checks or {})

    @router.get("/actuator/health/detail", tags=["Actuator"])
    async def health(request: Request):
        async def check(name, callback):
            try:
                async with asyncio.timeout(timeout):
                    value = await invoke(callback)
                return name, {"status": "up" if value else "down"}
            except Exception:
                return name, {"status": "down"}

        registered = request.app.state.host.services.get_service(HealthRegistry).checks()
        registered.update(checks)
        components = dict(await asyncio.gather(*(check(n, c) for n, c in registered.items())))
        healthy = all(item["status"] == "up" for item in components.values())
        return JSONResponse(
            {"status": "up" if healthy else "down", "components": components},
            status_code=200 if healthy else 503,
        )


def use_readiness(router):
    @router.get("/actuator/health/readiness", tags=["Actuator"])
    def readiness(request: Request):
        state = request.app.state.host.life.state
        return JSONResponse({"status": state}, status_code=200 if state == "up" else 503)


def use_liveness(router):
    @router.get("/actuator/health/liveness", tags=["Actuator"])
    def liveness():
        return {"status": "UP"}


def use_prometheus(router):
    @router.get("/actuator/prometheus", include_in_schema=False)
    def metrics(request: Request):
        return Response(
            generate_latest(request.app.state.metrics.registry),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )


def use_actuator(router):
    use_health(router)
    use_readiness(router)
    use_liveness(router)
    use_prometheus(router)
