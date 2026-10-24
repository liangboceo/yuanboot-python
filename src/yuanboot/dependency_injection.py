"""Constructor injection with singleton, request scope and transient lifetimes."""

from __future__ import annotations

import inspect
import threading
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any, get_args, get_origin, get_type_hints


class ServiceResolutionError(RuntimeError):
    pass


class ServiceLifetime(StrEnum):
    SINGLETON = "singleton"
    SCOPED = "scoped"
    TRANSIENT = "transient"


_UNSET = object()
_RESOLVING: ContextVar[tuple] = ContextVar("yuanboot_resolving", default=())


@dataclass(frozen=True)
class ServiceDescriptor:
    key: Any
    factory: Any
    lifetime: ServiceLifetime
    instance: Any = _UNSET


class ServiceCollection:
    def __init__(self) -> None:
        self._descriptors: dict[Any, ServiceDescriptor] = {}
        self.hosted_services: list[type] = []

    def _add(self, key, implementation, lifetime, instance=_UNSET):
        self._descriptors[key] = ServiceDescriptor(
            key, implementation if implementation is not None else key, lifetime, instance
        )
        return self

    def add_singleton(self, key, implementation=None, *, instance=_UNSET):
        return self._add(key, implementation, ServiceLifetime.SINGLETON, instance)

    def add_scoped(self, key, implementation=None):
        return self._add(key, implementation, ServiceLifetime.SCOPED)

    def add_transient(self, key, implementation=None):
        return self._add(key, implementation, ServiceLifetime.TRANSIENT)

    def add_hosted_service(self, implementation: type):
        self.add_singleton(implementation)
        if implementation not in self.hosted_services:
            self.hosted_services.append(implementation)
        return self

    def contains(self, key) -> bool:
        return key in self._descriptors

    def build(self) -> ServiceProvider:
        return ServiceProvider(dict(self._descriptors))


class ServiceProvider:
    def __init__(self, descriptors: dict, root: ServiceProvider | None = None):
        self._descriptors = descriptors
        self._root = root or self
        self._cache: dict = {}
        self._owned: list = []
        self._lock = root._lock if root else threading.RLock()
        self._closed = False

    def create_scope(self) -> ServiceProvider:
        self._ensure_open()
        return ServiceProvider(self._descriptors, self._root)

    def _ensure_open(self):
        if self._closed or self._root._closed:
            raise ServiceResolutionError("Service provider has been closed")

    def get_service(self, key):
        with self._lock:
            self._ensure_open()
            if key is ServiceProvider:
                return self
            descriptor = self._descriptors.get(key)
            if descriptor is None:
                raise ServiceResolutionError(f"Service {key!r} is not registered")
            if descriptor.instance is not _UNSET:
                return descriptor.instance
            stack = _RESOLVING.get()
            if any(item[0] == key for item in stack):
                chain = " -> ".join(
                    getattr(k, "__name__", str(k)) for k, _ in (*stack, (key, None))
                )
                raise ServiceResolutionError(f"Circular dependency: {chain}")
            if descriptor.lifetime == ServiceLifetime.SCOPED and (
                self is self._root or any(life == ServiceLifetime.SINGLETON for _, life in stack)
            ):
                raise ServiceResolutionError(f"Scoped service {key!r} requires an active scope")
            owner = self._root if descriptor.lifetime == ServiceLifetime.SINGLETON else self
            if descriptor.lifetime != ServiceLifetime.TRANSIENT and key in owner._cache:
                return owner._cache[key]
            token = _RESOLVING.set((*stack, (key, descriptor.lifetime)))
            try:
                value = owner._construct(descriptor.factory)
            finally:
                _RESOLVING.reset(token)
            if descriptor.lifetime != ServiceLifetime.TRANSIENT:
                owner._cache[key] = value
            if any(callable(getattr(value, method, None)) for method in ("aclose", "close")):
                if not any(item is value for item in owner._owned):
                    owner._owned.append(value)
            return value

    get_required_service = get_service

    def _construct(self, factory):
        if inspect.iscoroutinefunction(factory):
            raise ServiceResolutionError(
                "Use synchronous DI factories; initialize async resources on start"
            )
        target = factory.__init__ if inspect.isclass(factory) else factory
        try:
            hints = get_type_hints(target, include_extras=True)
            signature = inspect.signature(factory)
        except (TypeError, ValueError, NameError) as exc:
            raise ServiceResolutionError(f"Cannot inspect service {factory!r}: {exc}") from exc
        kwargs = {}
        for name, parameter in signature.parameters.items():
            if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
                continue
            annotation = hints.get(name, parameter.annotation)
            if get_origin(annotation) is Annotated:
                annotation = get_args(annotation)[0]
            if annotation not in self._descriptors and annotation is not ServiceProvider:
                if parameter.default is not parameter.empty:
                    continue
                raise ServiceResolutionError(
                    f"Unregistered dependency {name!r} ({annotation!r}) in {factory!r}"
                )
            if parameter.kind == parameter.POSITIONAL_ONLY:
                raise ServiceResolutionError("DI factories must accept keyword arguments")
            kwargs[name] = self.get_service(annotation)
        value = factory(**kwargs)
        if inspect.isawaitable(value):
            if inspect.iscoroutine(value):
                value.close()
            raise ServiceResolutionError("DI factories must return values, not awaitables")
        return value

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        errors = []
        for value in reversed(self._owned):
            try:
                result = (getattr(value, "aclose", None) or value.close)()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                errors.append(exc)
        self._owned.clear()
        self._cache.clear()
        if errors:
            raise ExceptionGroup("Service disposal failed", errors)

    async def __aenter__(self):
        self._ensure_open()
        return self

    async def __aexit__(self, *exc):
        await self.aclose()
