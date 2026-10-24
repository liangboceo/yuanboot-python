"""Nacos 1.x/2.x HTTP OpenAPI configuration and ephemeral service discovery."""

from __future__ import annotations

import asyncio
import json
import logging
import random
import socket
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, Field, SecretStr, model_validator

try:
    import httpx
except ImportError as exc:
    raise ImportError('Nacos requires: pip install "yuanboot[nacos]"') from exc

from yuanboot.branding import AUTHOR
from yuanboot.configuration import Configuration
from yuanboot.health import HealthRegistry
from yuanboot.hosting import ApplicationLife, BackgroundService, HostEnvironment, invoke

logger = logging.getLogger("yuanboot.nacos")


class NacosError(RuntimeError):
    def __init__(self, operation: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(
            f"Nacos {operation} failed" + (f" (HTTP {status_code})" if status_code else "")
        )


class NacosOptions(BaseModel):
    server_addr: str = "http://127.0.0.1:8848"
    context_path: str = "/nacos"
    namespace: str = ""
    group: str = "DEFAULT_GROUP"
    cluster: str = "DEFAULT"
    username: str = ""
    password: SecretStr = SecretStr("")
    timeout: float = Field(default=5, gt=0)
    data_id: str = ""
    format: str = "yaml"
    poll_interval: float = Field(default=5, gt=0)

    @model_validator(mode="after")
    def normalize(self):
        self.group = self.group or "DEFAULT_GROUP"
        self.cluster = self.cluster or "DEFAULT"
        if self.namespace == "public":
            self.namespace = ""
        if self.format not in {"yaml", "yml", "json"}:
            raise ValueError("Nacos config format must be yaml or json")
        return self

    @classmethod
    def from_configuration(cls, configuration: Configuration, section: str = ""):
        values = (
            configuration.get(section)
            if section
            else (
                configuration.get("yuanboot.cloud.nacos")
                or configuration.get("yuanboot.cloud.configcenter.nacos")
                or configuration.get("yuanboot.cloud.discovery.metadata", {})
            )
        )
        values = dict(values or {})
        if "url" in values and "server_addr" not in values:
            port = values.get("port", 8848)
            values["server_addr"] = ";".join(
                address if "://" in address else f"http://{address}:{port}"
                for address in values["url"].split(";")
            )
        auth = values.get("auth", {})
        if auth.get("enable", False):
            values.setdefault("username", auth.get("username", ""))
            values.setdefault("password", auth.get("password", ""))
        if "dataid" in values:
            values.setdefault("data_id", values["dataid"])
        configserver = values.get("configserver", {})
        values.setdefault("data_id", configserver.get("dataid", ""))
        return cls.model_validate(values)

    @classmethod
    def for_discovery(cls, configuration: Configuration):
        values = {
            **configuration.get("yuanboot.cloud.nacos", {}),
            **configuration.get("yuanboot.cloud.discovery.metadata", {}),
        }
        # A Go metadata URL explicitly selects a separate discovery endpoint.
        if "url" in configuration.get("yuanboot.cloud.discovery.metadata", {}):
            values.pop("server_addr", None)
        return cls.from_configuration(Configuration({"options": values}), "options")


@dataclass(frozen=True)
class ServiceInstance:
    service_name: str
    ip: str
    port: int
    group: str = "DEFAULT_GROUP"
    cluster: str = "DEFAULT"
    weight: float = 10.0
    healthy: bool = True
    enabled: bool = True
    ephemeral: bool = True
    metadata: dict[str, str] = field(default_factory=dict)


class NacosClient:
    name = "nacos"

    def __init__(self, options: NacosOptions, *, transport=None):
        self.options = options
        self._servers = []
        for address in options.server_addr.split(";"):
            parsed = urlsplit(address.strip())
            if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
                raise ValueError("Nacos server_addr must contain HTTP(S) URLs without credentials")
            context = parsed.path.rstrip("/") or options.context_path.rstrip("/")
            self._servers.append(f"{parsed.scheme}://{parsed.netloc}{context}")
        self._client = httpx.Client(timeout=options.timeout, trust_env=False, transport=transport)
        self._token = ""
        self._token_expires = 0.0
        self._auth_lock = threading.RLock()
        self._selection_lock = threading.Lock()
        self._selection = 0

    def _send(self, method, path, *, params=None, data=None):
        for index, server in enumerate(self._servers):
            try:
                response = self._client.request(method, server + path, params=params, data=data)
            except httpx.TransportError:
                if index == len(self._servers) - 1:
                    raise NacosError(path) from None
                continue
            if response.status_code >= 500 and index < len(self._servers) - 1:
                continue
            return response
        raise NacosError(path)

    def login(self):
        with self._auth_lock:
            if not self.options.username:
                return
            for path in ("/v1/auth/users/login", "/v1/auth/login"):
                response = self._send(
                    "POST",
                    path,
                    data={
                        "username": self.options.username,
                        "password": self.options.password.get_secret_value(),
                    },
                )
                if response.status_code == 404:
                    continue
                if response.status_code != 200:
                    raise NacosError("login", response.status_code)
                try:
                    payload = response.json()
                    token = payload["accessToken"]
                    ttl = float(payload.get("tokenTtl", 18000))
                except (ValueError, KeyError, TypeError):
                    raise NacosError("login response") from None
                if not isinstance(token, str) or not token:
                    raise NacosError("login response")
                self._token = token
                self._token_expires = time.monotonic() + max(1, ttl - 30)
                return
            raise NacosError("login endpoint", 404)

    def _request(self, method, path, *, params=None, data=None):
        for attempt in range(2):
            with self._auth_lock:
                if self.options.username and time.monotonic() >= self._token_expires:
                    self.login()
                token = self._token
            query, form = dict(params or {}), dict(data or {})
            if token:
                if method in {"POST", "PUT"}:
                    form["accessToken"] = token
                else:
                    query["accessToken"] = token
            response = self._send(method, path, params=query, data=form or None)
            if response.status_code in {401, 403} and attempt == 0 and self.options.username:
                with self._auth_lock:
                    self._token_expires = 0
                continue
            if not 200 <= response.status_code < 300:
                raise NacosError(path, response.status_code)
            return response
        raise NacosError(path)

    def get_config(self, data_id: str, *, group: str | None = None) -> str:
        return self._request(
            "GET",
            "/v1/cs/configs",
            params={
                "dataId": data_id,
                "group": group or self.options.group,
                "tenant": self.options.namespace,
            },
        ).text

    def publish_config(
        self, data_id: str, content: str, *, group: str | None = None, format: str = "yaml"
    ) -> bool:
        return (
            self._request(
                "POST",
                "/v1/cs/configs",
                data={
                    "dataId": data_id,
                    "group": group or self.options.group,
                    "tenant": self.options.namespace,
                    "content": content,
                    "type": format,
                },
            )
            .text.strip()
            .lower()
            == "true"
        )

    def delete_config(self, data_id: str, *, group: str | None = None) -> bool:
        return (
            self._request(
                "DELETE",
                "/v1/cs/configs",
                params={
                    "dataId": data_id,
                    "group": group or self.options.group,
                    "tenant": self.options.namespace,
                },
            )
            .text.strip()
            .lower()
            == "true"
        )

    def _instance_params(self, instance: ServiceInstance):
        return {
            "namespaceId": self.options.namespace,
            "serviceName": instance.service_name,
            "groupName": instance.group,
            "clusterName": instance.cluster,
            "ip": instance.ip,
            "port": instance.port,
            "ephemeral": str(instance.ephemeral).lower(),
        }

    def register(self, instance: ServiceInstance):
        params = self._instance_params(instance)
        params.update(
            weight=instance.weight,
            enabled=str(instance.enabled).lower(),
            healthy=str(instance.healthy).lower(),
            metadata=json.dumps(instance.metadata),
        )
        response = self._request("POST", "/v1/ns/instance", data=params)
        if response.text.strip().lower() != "ok":
            raise NacosError("register response")

    def unregister(self, instance: ServiceInstance):
        self._request("DELETE", "/v1/ns/instance", params=self._instance_params(instance))

    def get_services(self, *, page: int = 1, page_size: int = 100) -> list[str]:
        if page < 1 or not 1 <= page_size <= 1000:
            raise ValueError("Invalid Nacos service pagination")
        return (
            self._request(
                "GET",
                "/v1/ns/service/list",
                params={
                    "namespaceId": self.options.namespace,
                    "groupName": self.options.group,
                    "pageNo": page,
                    "pageSize": page_size,
                },
            )
            .json()
            .get("doms", [])
        )

    def delete_service(self, service_name: str):
        """Delete an empty service definition. Instances must be deregistered first."""
        self._request(
            "DELETE",
            "/v1/ns/service",
            params={
                "namespaceId": self.options.namespace,
                "groupName": self.options.group,
                "serviceName": service_name,
            },
        )

    def heartbeat(self, instance: ServiceInstance):
        params = self._instance_params(instance)
        params["beat"] = json.dumps(
            {
                "ip": instance.ip,
                "port": instance.port,
                "weight": instance.weight,
                "serviceName": f"{instance.group}@@{instance.service_name}",
                "cluster": instance.cluster,
                "metadata": instance.metadata,
                "scheduled": True,
            }
        )
        payload = self._request("PUT", "/v1/ns/instance/beat", data=params).json()
        if payload.get("code") == 20404:
            self.register(instance)
        elif payload.get("code", 10200) != 10200:
            raise NacosError("heartbeat response")
        return payload

    def get_instances(
        self, service_name: str, *, healthy_only: bool = True, group: str | None = None
    ) -> list[ServiceInstance]:
        group = group or self.options.group
        response = self._request(
            "GET",
            "/v1/ns/instance/list",
            params={
                "namespaceId": self.options.namespace,
                "serviceName": service_name,
                "groupName": group,
                "clusters": self.options.cluster,
                "healthyOnly": str(healthy_only).lower(),
            },
        )
        return [
            ServiceInstance(
                service_name=service_name,
                ip=host["ip"],
                port=host["port"],
                group=group,
                cluster=host.get("clusterName", "DEFAULT"),
                weight=host.get("weight", 1.0),
                healthy=host.get("healthy", True),
                enabled=host.get("enabled", True),
                ephemeral=host.get("ephemeral", True),
                metadata=host.get("metadata", {}),
            )
            for host in response.json().get("hosts", [])
            if not healthy_only
            or (host.get("healthy") and host.get("enabled", True) and host.get("weight", 1) > 0)
        ]

    def select_instance(self, service_name: str, *, strategy: str = "round-robin"):
        instances = self.get_instances(service_name)
        if not instances:
            raise LookupError(f"No healthy instances for {service_name}")
        if strategy == "random":
            return random.choices(instances, weights=[item.weight for item in instances])[0]
        if strategy != "round-robin":
            raise ValueError("Discovery strategy must be round-robin or random")
        with self._selection_lock:
            instance = instances[self._selection % len(instances)]
            self._selection += 1
            return instance

    async def watch_instances(self, service_name: str, *, interval: float = 5):
        if interval <= 0:
            raise ValueError("Watch interval must be positive")
        previous = None
        while True:
            instances = await asyncio.to_thread(self.get_instances, service_name)
            snapshot = sorted(instances, key=lambda item: (item.ip, item.port))
            if snapshot != previous:
                previous = snapshot
                yield snapshot
            await asyncio.sleep(interval)

    def ping(self) -> bool:
        try:
            response = self._request("GET", "/v1/console/health/readiness")
            return response.status_code == 200
        except NacosError:
            return False

    def close(self):
        self._client.close()


class NacosConfigurationSource:
    def __init__(self, options: NacosOptions, *, optional: bool = False, client=None):
        if not options.data_id:
            raise ValueError("Nacos configuration requires data_id")
        self.options = options
        self.client = client or NacosClient(options)
        self.optional = optional
        self._owns_client = client is None
        self.poll_interval = options.poll_interval

    def load(self) -> dict:
        try:
            content = self.client.get_config(self.options.data_id)
        except NacosError as exc:
            if self.optional and exc.status_code == 404:
                return {}
            raise
        values = json.loads(content) if self.options.format == "json" else yaml.safe_load(content)
        if values is None:
            return {}
        if not isinstance(values, dict):
            raise ValueError("Nacos configuration must contain a mapping")
        return values

    def close(self):
        if self._owns_client:
            self.client.close()


class NacosRegistration(BackgroundService):
    def __init__(
        self,
        client: NacosClient,
        configuration: Configuration,
        environment: HostEnvironment,
        life: ApplicationLife,
        health: HealthRegistry,
    ):
        super().__init__(life)
        from yuanboot.web.application import server_address

        self.client = client
        options = configuration.get_section("yuanboot.cloud.discovery")
        _, default_port = server_address(configuration)
        if configuration.get_string("yuanboot.grpc.address"):
            default_port = int(configuration.get_string("yuanboot.grpc.address").rsplit(":", 1)[1])
        self.enabled = options.get_bool("register-enable", True)
        ip = options.get_string("ip")
        if not ip:
            parsed = urlsplit(client.options.server_addr.split(";")[0])
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect((parsed.hostname, parsed.port or 8848))
                ip = probe.getsockname()[0]
        self.instance = ServiceInstance(
            service_name=options.get_string("service_name", environment.application_name),
            ip=ip,
            port=options.get_int("port", default_port),
            group=client.options.group,
            cluster=client.options.cluster,
            weight=float(options.get("weight", 10)),
            metadata={
                "yuanboot_version": environment.version,
                "yuanboot_env": environment.profile,
                "yuanboot_author": AUTHOR,
                "yuanboot_application_description": "quickly,quickly,quickly,quickly,quickly!!!!!",
                "yuanboot_application_context-path": options.get_string("metadata.path")
                or configuration.get_string("yuanboot.application.server.path"),
                "yuanboot_application_pid": str(environment.pid),
                "yuanboot_application_create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "yuanboot_application_name": environment.application_name,
                **{
                    str(key): str(value)
                    for key, value in {
                        **options.get("metadata.instance_metadata", {}),
                        **options.get("instance_metadata", {}),
                    }.items()
                },
            },
        )
        if not 1 <= self.instance.port <= 65535:
            raise ValueError("Nacos registration requires a concrete nonzero port")
        self.interval = float(options.get("heartbeat_interval", 5))
        if not 0 < self.interval <= 5:
            raise ValueError("Nacos heartbeat_interval must be in (0, 5] seconds")
        self._registered = False
        self._healthy = False
        if self.enabled:
            health.add(client.name, lambda: self._healthy)

    async def start(self):
        if self.enabled:
            self.life.subscribe("started", self._on_started)

    async def _on_started(self, event):
        await invoke(self.client.register, self.instance)
        self._registered = True
        self._healthy = True
        await super().start()

    async def execute(self):
        while True:
            await asyncio.sleep(self.interval)
            try:
                await invoke(self.client.heartbeat, self.instance)
                self._healthy = True
            except Exception:
                self._healthy = False
                logger.warning("%s heartbeat failed; will retry", self.client.name)

    async def stop(self):
        try:
            await super().stop()
        finally:
            if self._registered:
                await invoke(self.client.unregister, self.instance)
                self._registered = False
            self._healthy = False


def add_nacos_discovery(services):
    def client(configuration: Configuration) -> NacosClient:
        return NacosClient(NacosOptions.for_discovery(configuration))

    services.add_singleton(NacosClient, client)
    services.add_hosted_service(NacosRegistration)
    return services
