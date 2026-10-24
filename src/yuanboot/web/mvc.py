"""Controller routes preserve FastAPI's parameter binding and OpenAPI signatures."""

from __future__ import annotations

import inspect
from functools import wraps
from typing import Generic, TypeVar, get_type_hints

from fastapi import Depends, Request
from pydantic import BaseModel

from yuanboot.hosting import invoke

T = TypeVar("T")


class ApiResult(BaseModel, Generic[T]):
    success: bool = True
    message: str = "ok"
    data: T | None = None


class ApiController:
    def ok(self, data=None, message: str = "ok") -> ApiResult:
        return ApiResult(data=data, message=message)


def controller(prefix: str = "", *, tags: list[str] | None = None):
    def decorate(cls):
        cls.__yuanboot_controller__ = {"prefix": prefix, "tags": tags}
        return cls

    return decorate


def route(path: str, *, methods: list[str] | None = None, **options):
    def decorate(method):
        routes = list(getattr(method, "__yuanboot_routes__", []))
        routes.append((path, methods or ["GET"], options))
        method.__yuanboot_routes__ = routes
        return method

    return decorate


def _endpoint(controller_type, method):
    def resolve_controller(request: Request):
        return request.state.services.get_service(controller_type)

    @wraps(method)
    async def endpoint(**kwargs):
        instance = kwargs.pop("_yuanboot_controller")
        return await invoke(method.__get__(instance, controller_type), **kwargs)

    hints = get_type_hints(method, include_extras=True)
    signature = inspect.signature(method)
    parameters = [
        p.replace(annotation=hints.get(p.name, p.annotation))
        for p in list(signature.parameters.values())[1:]
    ]
    if any(p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in parameters):
        raise TypeError("Controller actions cannot use *args or **kwargs")
    parameters.append(
        inspect.Parameter(
            "_yuanboot_controller",
            inspect.Parameter.KEYWORD_ONLY,
            default=Depends(resolve_controller),
        )
    )
    endpoint.__signature__ = signature.replace(
        parameters=parameters, return_annotation=hints.get("return", signature.return_annotation)
    )
    return endpoint


class ControllerBuilder:
    def __init__(self, router, services):
        self.router = router
        self.services = services

    def add_controller(self, controller_type):
        from yuanboot.web.routing import RouterBuilder

        if not self.services.contains(controller_type):
            self.services.add_scoped(controller_type)
        options = getattr(controller_type, "__yuanboot_controller__", {})
        router = RouterBuilder(**options)
        # Declaration order is significant in FastAPI: /stats must precede /{id}.
        # inspect.getmembers sorts alphabetically and can silently reverse that order.
        methods_by_name = {}
        for base in reversed(controller_type.__mro__):
            methods_by_name.update(vars(base))
        for name, method in methods_by_name.items():
            if not inspect.isfunction(method):
                continue
            for path, methods, route_options in getattr(method, "__yuanboot_routes__", []):
                router.add_api_route(
                    path,
                    _endpoint(controller_type, method),
                    methods=methods,
                    name=f"{controller_type.__name__}.{name}",
                    **route_options,
                )
        self.router.include_router(router)
        return self
