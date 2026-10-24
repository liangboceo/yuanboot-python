from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from yuanboot.configuration import Configuration
from yuanboot.hosting import Host, HostBuilder
from yuanboot.web.middleware import HttpMetrics, RequestScopeMiddleware
from yuanboot.web.mvc import ControllerBuilder
from yuanboot.web.routing import RouterBuilder


def server_address(configuration: Configuration) -> tuple[str, int]:
    address = configuration.get_string("yuanboot.application.server.address")
    host = configuration.get_string("yuanboot.application.server.host", "0.0.0.0")
    port = configuration.get("yuanboot.application.server.port", 8080)
    if address:
        if ":" not in address:
            raise ValueError("Server address must be host:port or :port")
        address_host, address_port = address.rsplit(":", 1)
        host = address_host.strip("[]") or host
        port = int(address_port)
    port = int(configuration.get("port", port))
    if not 0 <= port <= 65535:
        raise ValueError("Server port must be between 0 and 65535")
    return host, port


class ApplicationBuilder:
    def __init__(self, app: FastAPI, services, configuration):
        self.app = app
        self.services = services
        self.configuration = configuration
        self.router = RouterBuilder()

    def use_endpoints(self, configure):
        configure(self.router)
        return self

    def use_mvc(self, configure):
        configure(ControllerBuilder(self.router, self.services))
        return self

    def use_middleware(self, middleware, **options):
        self.app.add_middleware(middleware, **options)
        return self

    def use_cors(self, *, allow_origins: list[str], **options):
        return self.use_middleware(CORSMiddleware, allow_origins=allow_origins, **options)

    def use_static(self, prefix: str = "/static", directory: str | Path = "static"):
        self.app.mount(prefix, StaticFiles(directory=directory), name="static")
        return self

    def use_views(self, directory: str | Path = "templates"):
        self.services.add_singleton(Jinja2Templates, instance=Jinja2Templates(directory=directory))
        return self


class WebApplication(Host):
    def __init__(self, app: FastAPI, *args):
        super().__init__(*args)
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)

    def run(self, *, host: str | None = None, port: int | None = None, **options):
        configured_host, configured_port = server_address(self.configuration)
        tls = self.configuration.get_section("yuanboot.application.server.tls")
        if tls.get_string("cert"):
            options.setdefault("ssl_certfile", tls.get_string("cert"))
            options.setdefault("ssl_keyfile", tls.get_string("key"))
        uvicorn.run(
            self.app,
            host=host or configured_host,
            port=port if port is not None else configured_port,
            **options,
        )

    @staticmethod
    def create_default_builder(configure=None, **options):
        return create_default_builder(configure, **options)


class WebHostBuilder(HostBuilder):
    def __init__(self, configuration: Configuration | None = None, **fastapi_options):
        super().__init__(configuration)
        if "lifespan" in fastapi_options:
            raise ValueError("Use hosted services/lifecycle events to extend the managed lifespan")
        self._fastapi_options = fastapi_options
        self._configures: list = []

    def configure(self, configure):
        self._configures.append(configure)
        return self

    def build(self) -> WebApplication:
        environment, life = self._prepare()

        @asynccontextmanager
        async def lifespan(app):
            await host.start()
            try:
                yield
            finally:
                await host.stop()

        options = {"title": environment.application_name, "version": environment.version}
        options.update(self._fastapi_options)
        app = FastAPI(lifespan=lifespan, **options)
        builder = ApplicationBuilder(app, self.services, self.configuration)
        for configure in self._configures:
            configure(builder)
        app.include_router(builder.router)
        # FastAPI's own dependencies can access the same application/container.
        self.services.add_singleton(FastAPI, instance=app)
        metrics = HttpMetrics()
        self.services.add_singleton(HttpMetrics, instance=metrics)
        provider = self.services.build()
        host = WebApplication(
            app, provider, self.configuration, environment, life, self.services.hosted_services
        )
        app.state.host = host
        app.state.services = provider
        app.state.metrics = metrics
        app.add_middleware(RequestScopeMiddleware, services=provider, metrics=metrics)
        return host


def create_default_builder(configure=None, **options) -> WebHostBuilder:
    builder = WebHostBuilder(**options)
    if configure is not None:
        builder.configure(lambda app: app.use_endpoints(configure))
    return builder


create_http_builder = create_default_builder
