"""Common discovery contract and memory/Consul/Eureka/etcd v3 HTTP adapters."""

from __future__ import annotations

import asyncio
import base64
import json
import random
import threading
from dataclasses import asdict
from typing import Protocol
from urllib.parse import quote

import httpx
from pydantic import Field, SecretStr

from yuanboot.components.nacos import NacosOptions, ServiceInstance
from yuanboot.configuration import Configuration
from yuanboot.dependency_injection import ServiceProvider
from yuanboot.health import HealthRegistry
from yuanboot.hosting import ApplicationLife, HostEnvironment


class ServiceDiscovery(Protocol):
    def register(self, instance: ServiceInstance): ...
    def unregister(self, instance: ServiceInstance): ...
    def heartbeat(self, instance: ServiceInstance): ...
    def get_instances(self, service_name: str, *, healthy_only=True): ...
    def select_instance(self, service_name: str, *, strategy="round-robin"): ...


class RegistryOptions(NacosOptions):
    server_addr: str = "http://127.0.0.1:8500"
    token: SecretStr = SecretStr("")
    ttl: int = Field(default=15, ge=10)
    prefix: str = "/yuanboot"


class DiscoveryError(RuntimeError):
    pass


class RegistryClient:
    name = "registry"

    def __init__(self, options: RegistryOptions, *, transport=None):
        self.options = options
        self.client = httpx.Client(
            base_url=options.server_addr.rstrip("/"),
            timeout=options.timeout,
            transport=transport,
            trust_env=False,
        )
        self._cursor = {}
        self._lock = threading.RLock()

    def request(self, method, path, **kwargs):
        try:
            response = self.client.request(method, path, **kwargs)
        except httpx.TransportError:
            raise DiscoveryError(f"{self.name} unavailable") from None
        if not response.is_success:
            raise DiscoveryError(f"{self.name} request failed (HTTP {response.status_code})")
        return response

    def select_instance(self, service_name, *, strategy="round-robin"):
        instances = self.get_instances(service_name)
        if not instances:
            raise LookupError(f"No healthy instances for {service_name}")
        if strategy == "random":
            return random.choices(instances, weights=[item.weight for item in instances])[0]
        if strategy != "round-robin":
            raise ValueError("Discovery strategy must be round-robin or random")
        with self._lock:
            index = self._cursor.get(service_name, 0)
            self._cursor[service_name] = index + 1
            return instances[index % len(instances)]

    async def watch_instances(self, service_name, *, interval=5):
        if interval <= 0:
            raise ValueError("Watch interval must be positive")
        previous = None
        while True:
            instances = await asyncio.to_thread(self.get_instances, service_name)
            instances.sort(key=lambda item: (item.ip, item.port))
            if instances != previous:
                previous = instances
                yield instances
            await asyncio.sleep(interval)

    def close(self):
        self.client.close()


def _id(instance):
    return f"{instance.service_name}:{instance.ip}:{instance.port}"


class MemoryDiscovery(RegistryClient):
    name = "memory"

    def __init__(self, options=None):
        super().__init__(options or RegistryOptions(server_addr="http://127.0.0.1"))
        self._instances = {}

    def register(self, instance):
        with self._lock:
            self._instances[_id(instance)] = instance

    def unregister(self, instance):
        with self._lock:
            self._instances.pop(_id(instance), None)

    def heartbeat(self, instance):
        self.register(instance)

    def get_instances(self, service_name, *, healthy_only=True):
        with self._lock:
            return [
                item
                for item in self._instances.values()
                if item.service_name == service_name
                and (not healthy_only or (item.healthy and item.enabled and item.weight > 0))
            ]

    def get_services(self):
        with self._lock:
            return sorted({item.service_name for item in self._instances.values()})

    def ping(self):
        return True


class ConsulClient(RegistryClient):
    name = "consul"

    def __init__(self, options, **kwargs):
        super().__init__(options, **kwargs)
        if options.token.get_secret_value():
            self.client.headers["X-Consul-Token"] = options.token.get_secret_value()
        if options.namespace:
            self.client.headers["X-Consul-Namespace"] = options.namespace

    def register(self, instance):
        self.request(
            "PUT",
            "/v1/agent/service/register",
            json={
                "ID": _id(instance),
                "Name": instance.service_name,
                "Address": instance.ip,
                "Port": instance.port,
                "Meta": instance.metadata,
                "Weights": {"Passing": max(1, int(instance.weight)), "Warning": 1},
                "Check": {
                    "TTL": f"{self.options.ttl}s",
                    "Status": "passing",
                    "DeregisterCriticalServiceAfter": "1m",
                },
            },
        )

    def unregister(self, instance):
        self.request("PUT", "/v1/agent/service/deregister/" + quote(_id(instance), safe=""))

    def heartbeat(self, instance):
        try:
            self.request(
                "PUT", "/v1/agent/check/pass/" + quote("service:" + _id(instance), safe="")
            )
        except DiscoveryError:
            self.register(instance)

    def get_instances(self, service_name, *, healthy_only=True):
        payload = self.request(
            "GET",
            "/v1/health/service/" + quote(service_name, safe=""),
            params={"passing": str(healthy_only).lower()},
        ).json()
        instances = []
        for item in payload:
            service = item["Service"]
            healthy = all(check["Status"] == "passing" for check in item.get("Checks", []))
            instance = ServiceInstance(
                service_name,
                service["Address"] or item["Node"]["Address"],
                service["Port"],
                healthy=healthy,
                weight=service.get("Weights", {}).get("Passing", 10),
                metadata=service.get("Meta") or {},
            )
            if not healthy_only or (healthy and instance.weight > 0):
                instances.append(instance)
        return instances

    def get_services(self):
        return sorted(self.request("GET", "/v1/catalog/services").json())

    def ping(self):
        return bool(self.request("GET", "/v1/status/leader").json())


class EurekaClient(RegistryClient):
    name = "eureka"

    def __init__(self, options, **kwargs):
        super().__init__(options, **kwargs)
        self.client.headers["Accept"] = "application/json"
        if options.username:
            self.client.auth = (options.username, options.password.get_secret_value())

    def _path(self, name="", instance=None):
        base = "/apps" + ("/" + quote(name.upper(), safe="") if name else "")
        return base + ("/" + quote(_id(instance), safe="") if instance else "")

    def register(self, instance):
        self.request(
            "POST",
            self._path(instance.service_name),
            json={
                "instance": {
                    "instanceId": _id(instance),
                    "app": instance.service_name.upper(),
                    "hostName": instance.ip,
                    "ipAddr": instance.ip,
                    "status": "UP",
                    "port": {"$": instance.port, "@enabled": "true"},
                    "vipAddress": instance.service_name,
                    "metadata": instance.metadata,
                    "leaseInfo": {"renewalIntervalInSecs": 5, "durationInSecs": self.options.ttl},
                    "dataCenterInfo": {
                        "@class": "com.netflix.appinfo.InstanceInfo$DefaultDataCenterInfo",
                        "name": "MyOwn",
                    },
                }
            },
        )

    def unregister(self, instance):
        self.request("DELETE", self._path(instance.service_name, instance))

    def heartbeat(self, instance):
        try:
            self.request("PUT", self._path(instance.service_name, instance))
        except DiscoveryError:
            self.register(instance)

    def get_instances(self, service_name, *, healthy_only=True):
        response = self.client.get(self._path(service_name))
        if response.status_code == 404:
            return []
        if not response.is_success:
            raise DiscoveryError(f"eureka request failed (HTTP {response.status_code})")
        items = response.json().get("application", {}).get("instance", [])
        if isinstance(items, dict):
            items = [items]
        return [
            ServiceInstance(
                service_name,
                item["ipAddr"],
                int(item["port"]["$"]),
                healthy=item["status"] == "UP",
                metadata=item.get("metadata", {}),
            )
            for item in items
            if not healthy_only or item["status"] == "UP"
        ]

    def get_services(self):
        items = self.request("GET", "/apps").json().get("applications", {}).get("application", [])
        if isinstance(items, dict):
            items = [items]
        return sorted(item["name"] for item in items)

    def ping(self):
        self.get_services()
        return True


def _b64(value):
    return base64.b64encode(value.encode()).decode()


class EtcdClient(RegistryClient):
    """Uses the etcd v3 JSON gRPC gateway and one lease per registered instance."""

    name = "etcd"

    def __init__(self, options, **kwargs):
        super().__init__(options, **kwargs)
        self._leases = {}
        if options.username:
            token = self.request(
                "POST",
                "/v3/auth/authenticate",
                json={"name": options.username, "password": options.password.get_secret_value()},
            ).json()["token"]
            self.client.headers["Authorization"] = token

    def _prefix(self, name=""):
        options = self.options
        root = (
            "/".join(
                [
                    options.prefix.rstrip("/"),
                    quote(options.namespace, safe=""),
                    quote(options.group, safe=""),
                ]
            )
            + "/"
        )
        return root + (quote(name, safe="") + "/" if name else "")

    def register(self, instance):
        lease = self.request("POST", "/v3/lease/grant", json={"TTL": self.options.ttl}).json()["ID"]
        key = self._prefix(instance.service_name) + quote(_id(instance), safe="")
        try:
            self.request(
                "POST",
                "/v3/kv/put",
                json={
                    "key": _b64(key),
                    "value": _b64(json.dumps(asdict(instance))),
                    "lease": lease,
                },
            )
        except BaseException:
            self.request("POST", "/v3/lease/revoke", json={"ID": lease})
            raise
        previous = self._leases.get(_id(instance))
        self._leases[_id(instance)] = lease
        if previous:
            self.request("POST", "/v3/lease/revoke", json={"ID": previous})

    def unregister(self, instance):
        lease = self._leases.pop(_id(instance), None)
        if lease:
            self.request("POST", "/v3/lease/revoke", json={"ID": lease})

    def heartbeat(self, instance):
        lease = self._leases.get(_id(instance))
        if lease:
            # The gateway streams responses; close after the first keepalive acknowledgement.
            with self.client.stream("POST", "/v3/lease/keepalive", json={"ID": lease}) as response:
                if response.is_success:
                    for line in response.iter_lines():
                        payload = json.loads(line).get("result", {})
                        if int(payload.get("TTL", 0)) > 0:
                            return
                        break
        self.register(instance)

    def _range(self, prefix):
        # A slash-terminated prefix has the exclusive range end with the slash incremented.
        payload = self.request(
            "POST", "/v3/kv/range", json={"key": _b64(prefix), "range_end": _b64(prefix[:-1] + "0")}
        ).json()
        return [
            ServiceInstance(**json.loads(base64.b64decode(item["value"])))
            for item in payload.get("kvs", [])
        ]

    def get_instances(self, service_name, *, healthy_only=True):
        return [
            item
            for item in self._range(self._prefix(service_name))
            if not healthy_only or (item.healthy and item.enabled and item.weight > 0)
        ]

    def get_services(self):
        return sorted({item.service_name for item in self._range(self._prefix())})

    def ping(self):
        return str(self.request("GET", "/health").json().get("health")).lower() == "true"


def add_service_discovery(services):
    from yuanboot.components.nacos import NacosClient, NacosRegistration

    def factory(configuration: Configuration, provider: ServiceProvider):
        kind = configuration.get_string("yuanboot.cloud.discovery.type", "memory")
        if kind == "nacos":
            return provider.get_service(NacosClient)
        values = configuration.get("yuanboot.cloud.discovery.metadata", {})
        defaults = {
            "memory": "http://127.0.0.1",
            "consul": "http://127.0.0.1:8500",
            "etcd": "http://127.0.0.1:2379",
            "eureka": "http://127.0.0.1:8761/eureka",
        }
        adapters = {
            "memory": MemoryDiscovery,
            "consul": ConsulClient,
            "etcd": EtcdClient,
            "eureka": EurekaClient,
        }
        if kind not in adapters:
            raise ValueError(f"Unknown discovery type: {kind}")
        values = dict(values)
        address = values.pop("address", defaults[kind])
        if isinstance(address, list):
            address = address[0]
        values.setdefault("server_addr", values.pop("url", address))
        if not values["server_addr"].startswith(("http://", "https://")):
            values["server_addr"] = "http://" + values["server_addr"]
        auth = values.get("auth", {})
        if auth.get("enable"):
            values.setdefault("username", auth.get("username", ""))
            values.setdefault("password", auth.get("password", ""))
        return adapters[kind](RegistryOptions.model_validate(values))

    def registration(
        client: ServiceDiscovery,
        configuration: Configuration,
        environment: HostEnvironment,
        life: ApplicationLife,
        health: HealthRegistry,
    ):
        return NacosRegistration(client, configuration, environment, life, health)

    # Reuse the metadata/lifecycle implementation for every registry.
    services.add_singleton(ServiceDiscovery, factory)
    if not services.contains(NacosClient):

        def nacos_factory(configuration: Configuration):
            return NacosClient(NacosOptions.for_discovery(configuration))

        services.add_singleton(NacosClient, nacos_factory)
    services.add_hosted_service(NacosRegistration)
    services.add_singleton(NacosRegistration, registration)
    return services
