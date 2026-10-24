import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from yuanboot import ServiceCollection, ServiceProvider, ServiceResolutionError


class Singleton:
    pass


class Scoped:
    def __init__(self, singleton: Singleton):
        self.singleton = singleton


class Transient:
    def __init__(self, scoped: Scoped):
        self.scoped = scoped


class Captive:
    def __init__(self, transient: Transient):
        self.transient = transient


class CycleA:
    def __init__(self, other: "CycleB"):
        self.other = other


class CycleB:
    def __init__(self, other: CycleA):
        self.other = other


def test_lifetimes_and_thread_safe_singleton():
    provider = (
        ServiceCollection()
        .add_singleton(Singleton)
        .add_scoped(Scoped)
        .add_transient(Transient)
        .build()
    )
    with ThreadPoolExecutor(max_workers=8) as executor:
        instances = list(executor.map(lambda _: provider.get_service(Singleton), range(32)))
    assert all(instance is instances[0] for instance in instances)
    a, b = provider.create_scope(), provider.create_scope()
    assert a.get_service(Scoped) is a.get_service(Scoped)
    assert a.get_service(Scoped) is not b.get_service(Scoped)
    assert a.get_service(Scoped).singleton is b.get_service(Scoped).singleton
    one, two = a.get_service(Transient), a.get_service(Transient)
    assert one is not two and one.scoped is two.scoped


def test_scope_and_cycle_errors():
    provider = (
        ServiceCollection()
        .add_singleton(Singleton)
        .add_scoped(Scoped)
        .add_transient(Transient)
        .add_singleton(Captive)
        .add_transient(CycleA)
        .add_transient(CycleB)
        .build()
    )
    with pytest.raises(ServiceResolutionError, match="active scope"):
        provider.get_service(Scoped)
    with pytest.raises(ServiceResolutionError, match="active scope"):
        provider.create_scope().get_service(Captive)
    with pytest.raises(ServiceResolutionError, match="Circular dependency"):
        provider.get_service(CycleA)
    with pytest.raises(ServiceResolutionError, match="not registered"):
        provider.get_service(str)


def test_factories_defaults_and_explicit_instances():
    external = Singleton()

    def factory(provider: ServiceProvider, prefix: str = "default"):
        assert provider.get_service(Singleton) is external
        return (prefix,)

    provider = (
        ServiceCollection()
        .add_singleton(Singleton, instance=external)
        .add_transient(tuple, factory)
        .build()
    )
    assert provider.get_service(tuple) == ("default",)


def test_reverse_async_disposal_continues_on_error():
    disposed = []

    class Resource:
        async def aclose(self):
            disposed.append("resource")

    class Broken:
        def close(self):
            disposed.append("broken")
            raise RuntimeError("dispose failed")

    async def scenario():
        provider = ServiceCollection().add_scoped(Resource).add_transient(Broken).build()
        scope = provider.create_scope()
        scope.get_service(Resource)
        scope.get_service(Broken)
        with pytest.raises(ExceptionGroup):
            await scope.aclose()
        assert disposed == ["broken", "resource"]
        await scope.aclose()
        with pytest.raises(ServiceResolutionError, match="closed"):
            scope.get_service(Resource)
        await provider.aclose()

    asyncio.run(scenario())


def test_async_factory_rejected():
    async def factory():
        return Singleton()

    with pytest.raises(ServiceResolutionError, match="synchronous"):
        ServiceCollection().add_singleton(Singleton, factory).build().get_service(Singleton)
