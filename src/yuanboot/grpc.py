"""grpc.aio transport sharing configuration, DI and host lifecycle with HTTP/console."""

from __future__ import annotations

import asyncio

try:
    import grpc
    from grpc_health.v1 import health_pb2, health_pb2_grpc
    from grpc_health.v1._async import HealthServicer
except ImportError as exc:
    raise ImportError('gRPC requires: pip install "yuanboot[grpc]"') from exc

from yuanboot.configuration import Configuration
from yuanboot.dependency_injection import ServiceProvider
from yuanboot.health import HealthRegistry
from yuanboot.hosting import HostBuilder, HostedService


class GrpcServer(HostedService):
    def __init__(
        self,
        configuration: Configuration,
        provider: ServiceProvider,
        health: HealthRegistry,
        configure,
        *,
        interceptors=(),
        credentials=None,
    ):
        self.configuration, self.provider, self.configure = configuration, provider, configure
        self.interceptors, self.credentials = interceptors, credentials
        self.server = None
        self.port = 0
        self._serving = False
        health.add("grpc", lambda: self._serving)

    async def start(self):
        self.server = grpc.aio.server(interceptors=self.interceptors)
        self.health_service = HealthServicer()
        health_pb2_grpc.add_HealthServicer_to_server(self.health_service, self.server)
        try:
            # Registration must run in the server's event-loop thread (grpc.aio).
            import inspect

            result = self.configure(self.server, self.provider)
            if inspect.isawaitable(result):
                await result
            address = self.configuration.get_string("yuanboot.grpc.address", "0.0.0.0:9090")
            self.port = (
                self.server.add_secure_port(address, self.credentials)
                if self.credentials
                else self.server.add_insecure_port(address)
            )
            if self.port == 0:
                raise RuntimeError("gRPC failed to bind address")
            await self.server.start()
            self._serving = True
            await self.health_service.set("", health_pb2.HealthCheckResponse.SERVING)
        except BaseException:
            await self.server.stop(0)
            raise

    async def stop(self):
        self._serving = False
        if self.server is not None:
            await self.health_service.enter_graceful_shutdown()
            grace = float(self.configuration.get("yuanboot.grpc.shutdown_grace", 5))
            await self.server.stop(grace)


class GrpcHostBuilder(HostBuilder):
    def __init__(self, configuration=None):
        super().__init__(configuration)
        self._configure_server = lambda server, services: None
        self._interceptors = ()
        self._credentials = None

    def configure_server(self, configure, *, interceptors=(), credentials=None):
        self._configure_server, self._interceptors, self._credentials = (
            configure,
            interceptors,
            credentials,
        )
        return self

    def build(self):
        def register(services):
            def factory(
                configuration: Configuration, provider: ServiceProvider, health: HealthRegistry
            ):
                return GrpcServer(
                    configuration,
                    provider,
                    health,
                    self._configure_server,
                    interceptors=self._interceptors,
                    credentials=self._credentials,
                )

            services.add_hosted_service(GrpcServer)
            services.add_singleton(GrpcServer, factory)

        self.configure_services(register)
        return super().build()


class GrpcClientFactory:
    """Create channels in the active event loop. Discovery resolves once per create call."""

    def __init__(self, discovery=None):
        self.discovery = discovery
        self._channels = {}

    def create(self, target: str, *, credentials=None):
        if target.startswith("lb://"):
            if self.discovery is None:
                raise RuntimeError("lb:// requires a discovery client")
            instance = self.discovery.select_instance(target[5:])
            host = f"[{instance.ip}]" if ":" in instance.ip else instance.ip
            target = f"{host}:{instance.port}"
        key = (target, id(credentials))
        if key not in self._channels:
            self._channels[key] = (
                grpc.aio.secure_channel(target, credentials)
                if credentials
                else grpc.aio.insecure_channel(target)
            )
        return self._channels[key]

    async def aclose(self):
        await asyncio.gather(*(channel.close() for channel in self._channels.values()))
        self._channels.clear()
