"""Shared web/console host, application events and managed background services."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import signal
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from starlette.concurrency import run_in_threadpool

from yuanboot._version import __version__
from yuanboot.branding import NOTICE
from yuanboot.configuration import Configuration, ConfigurationBuilder
from yuanboot.dependency_injection import ServiceCollection, ServiceProvider
from yuanboot.environment import validate_profile
from yuanboot.health import HealthRegistry

logger = logging.getLogger("yuanboot")


async def invoke(callback: Callable, *args, **kwargs):
    if inspect.iscoroutinefunction(callback):
        return await callback(*args, **kwargs)
    result = await run_in_threadpool(callback, *args, **kwargs)
    return await result if inspect.isawaitable(result) else result


@dataclass(frozen=True)
class HostEnvironment:
    application_name: str = "yuanboot"
    profile: str = "dev"
    pid: int = field(default_factory=os.getpid)
    version: str = __version__

    def __post_init__(self):
        validate_profile(self.profile)

    @property
    def is_development(self) -> bool:
        return self.profile == "dev"

    @property
    def is_fat(self) -> bool:
        return self.profile == "fat"

    @property
    def is_uat(self) -> bool:
        return self.profile == "uat"

    @property
    def is_production(self) -> bool:
        return self.profile == "pro"


@dataclass(frozen=True)
class ApplicationEvent:
    topic: str
    data: Any = None


class ApplicationLife:
    def __init__(self):
        self.state = "down"
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)

    def subscribe(self, topic: str, callback: Callable) -> ApplicationLife:
        self._subscribers[topic].append(callback)
        return self

    async def publish(self, topic: str, data: Any = None):
        for callback in tuple(self._subscribers[topic]):
            await invoke(callback, ApplicationEvent(topic, data))


class HostedService:
    async def start(self) -> None:
        """Initialize the service. Long-running work belongs in BackgroundService.execute."""

    async def stop(self) -> None:
        """Release resources allocated by start."""


class BackgroundService(HostedService):
    """A cancellable task. Override execute; use finally for task-local cleanup."""

    def __init__(self, life: ApplicationLife):
        self.life = life
        self._task: asyncio.Task | None = None

    async def execute(self) -> None:
        raise NotImplementedError

    async def start(self) -> None:
        self._task = asyncio.create_task(self.execute(), name=type(self).__name__)
        self._task.add_done_callback(self._completed)

    def _completed(self, task: asyncio.Task):
        if not task.cancelled() and (error := task.exception()) is not None:
            self.life.state = "failed"
            logger.error("Background service failed: %s", type(self).__name__, exc_info=error)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass


class Host:
    def __init__(self, services, configuration, environment, life, hosted_services):
        self.services: ServiceProvider = services
        self.configuration: Configuration = configuration
        self.environment: HostEnvironment = environment
        self.life: ApplicationLife = life
        self._hosted_types = tuple(hosted_services)
        self._started_services: list = []
        self._phase = "created"

    async def start(self):
        if self._phase != "created":
            raise RuntimeError("A host can start once; create a new host for another lifecycle")
        self._phase = "starting"
        self.life.state = "starting"
        try:
            from yuanboot.logging import LoggingManager

            self.services.get_service(LoggingManager).print_banner()
            logger.info(NOTICE)
            logger.info(
                "Welcome to yuanboot, starting application ...",
                extra={"_yuanboot_color": "green"},
            )
            for message, value, color in (
                ("yuanboot framework version :  %s", __version__, "blue"),
                ("application running pid  :  %s", self.environment.pid, "blue"),
                ("application name         :  %s", self.environment.application_name, "blue"),
                ("application exec path    :  %s", os.getcwd(), "yellow"),
                ("application environment  :  %s", self.environment.profile, "blue"),
                (
                    "running in %s mode , set YUANBOOT_PROFILE to dev / fat / uat / pro.",
                    self.environment.profile,
                    "red",
                ),
            ):
                logger.info(message, value, extra={"_yuanboot_value_color": color})
            logger.info("Starting server...", extra={"_yuanboot_color": "green"})
            await self.life.publish("starting", self)
            for service_type in self._hosted_types:
                service = self.services.get_service(service_type)
                self._started_services.append(service)
                await invoke(service.start)
            # Background tasks may fail before all hosted services finish initializing.
            if self.life.state == "failed":
                raise RuntimeError("A background service failed during startup")
            self.life.state = "up"
            self._phase = "started"
            await self.life.publish("started", self)
            logger.info("Server is Started.", extra={"_yuanboot_color": "green"})
        except BaseException:
            try:
                await self.stop()
            except Exception:
                logger.exception("Cleanup after failed startup")
            raise

    async def stop(self):
        if self._phase == "stopped":
            return
        self._phase = "stopped"
        self.life.state = "down"
        errors = []

        async def cleanup(callback, *args):
            try:
                await invoke(callback, *args)
            except Exception as exc:
                errors.append(exc)

        await cleanup(self.life.publish, "stopping", self)
        for service in reversed(self._started_services):
            await cleanup(service.stop)
        self._started_services.clear()
        await cleanup(self.life.publish, "stopped", self)
        await cleanup(self.services.aclose)
        if errors:
            raise ExceptionGroup("Host shutdown failed", errors)

    async def run_async(self, stop_event: asyncio.Event | None = None):
        event = stop_event or asyncio.Event()
        loop = asyncio.get_running_loop()
        signals = []
        if stop_event is None:
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, event.set)
                    signals.append(sig)
                except (NotImplementedError, RuntimeError, ValueError):
                    pass
        try:
            await self.start()
            await event.wait()
        finally:
            try:
                await self.stop()
            finally:
                for sig in signals:
                    loop.remove_signal_handler(sig)

    def run(self):
        asyncio.run(self.run_async())


class HostBuilder:
    def __init__(self, configuration: Configuration | None = None):
        self.configuration = (
            configuration
            if configuration is not None
            else (ConfigurationBuilder().add_yaml_file(optional=True).add_environment().build())
        )
        self.services = ServiceCollection()
        self._service_configures: list[Callable] = []
        self._life_configures: list[Callable] = []
        self._built = False

    def use_configuration(self, configuration: Configuration):
        self.configuration = configuration
        return self

    def set_environment(self, profile: str):
        self.configuration = Configuration(self.configuration.to_dict(), profile=profile)
        return self

    def configure_services(self, configure: Callable[[ServiceCollection], None]):
        self._service_configures.append(configure)
        return self

    def use_startup(self, startup):
        instance = startup() if inspect.isclass(startup) else startup
        self.configure_services(instance.configure_services)
        if hasattr(instance, "configure") and hasattr(self, "configure"):
            self.configure(instance.configure)
        return self

    def on_application_life_event(self, configure: Callable[[ApplicationLife], None]):
        self._life_configures.append(configure)
        return self

    def use_mysql(self):
        from yuanboot.components.mysql import add_mysql

        return self.configure_services(add_mysql)

    def use_redis(self):
        from yuanboot.components.redis import add_redis

        return self.configure_services(add_redis)

    def use_nacos_discovery(self):
        from yuanboot.components.nacos import add_nacos_discovery

        return self.configure_services(add_nacos_discovery)

    def use_service_discovery(self):
        from yuanboot.components.discovery import add_service_discovery

        return self.configure_services(add_service_discovery)

    def use_logging(self):
        from yuanboot.logging import add_logging

        return self.configure_services(add_logging)

    def use_http_client(self):
        from yuanboot.components.httpclient import add_http_client

        return self.configure_services(add_http_client)

    def use_email(self):
        from yuanboot.components.email import add_email

        return self.configure_services(add_email)

    def use_scheduler(self, configure=None):
        from yuanboot.components.scheduler import add_scheduler

        return self.configure_services(lambda services: add_scheduler(services, configure))

    def use_components(self):
        """Enable infrastructure declared in configuration, including Go-style datasource keys."""
        configuration = self.configuration
        if configuration.get("yuanboot.logging") is not None:
            self.use_logging()
        database = configuration.get("yuanboot.datasource.mysql")
        if (
            database is not None
            or configuration.get_string("yuanboot.datasource.db.type") == "mysql"
        ):
            self.use_mysql()
        if configuration.get("yuanboot.datasource.redis") is not None:
            self.use_redis()
        if configuration.get_string("yuanboot.cloud.discovery.type"):
            self.use_service_discovery()
        if configuration.get("yuanboot.httpclient") is not None:
            self.use_http_client()
        if configuration.get("yuanboot.email") is not None:
            self.use_email()
        return self

    def _prepare(self):
        if self._built:
            raise RuntimeError("A builder can only build once")
        self._built = True
        life = ApplicationLife()
        environment = HostEnvironment(
            application_name=self.configuration.get_string("app")
            or self.configuration.get_string("yuanboot.application.name", "yuanboot"),
            profile=self.configuration.profile,
        )
        for key, value in (
            (Configuration, self.configuration),
            (ApplicationLife, life),
            (HostEnvironment, environment),
        ):
            self.services.add_singleton(key, instance=value)
        self.services.add_singleton(HealthRegistry)
        if self.configuration._sources:
            from yuanboot.components.configuration import ConfigurationMonitor

            self.services.add_hosted_service(ConfigurationMonitor)
        for configure in self._service_configures:
            configure(self.services)
        from yuanboot.logging import LoggingManager, add_logging

        if not self.services.contains(LoggingManager):
            add_logging(self.services)
        for configure in self._life_configures:
            configure(life)
        return environment, life

    def build(self) -> Host:
        environment, life = self._prepare()
        return Host(
            self.services.build(),
            self.configuration,
            environment,
            life,
            self.services.hosted_services,
        )


def create_default_builder() -> HostBuilder:
    return HostBuilder()
