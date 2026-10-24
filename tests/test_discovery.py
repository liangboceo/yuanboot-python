import asyncio
import base64
import json

import httpx
import pytest

from yuanboot import Configuration, HostBuilder
from yuanboot.components.discovery import (
    ConsulClient,
    EtcdClient,
    EurekaClient,
    MemoryDiscovery,
    RegistryOptions,
    ServiceDiscovery,
)
from yuanboot.components.nacos import NacosRegistration, ServiceInstance


def test_memory_registration_host_lifecycle_and_watch():
    async def scenario():
        host = (
            HostBuilder(
                Configuration(
                    {
                        "yuanboot": {
                            "cloud": {
                                "discovery": {"type": "memory", "ip": "127.0.0.1", "port": 8000}
                            }
                        }
                    }
                )
            )
            .use_components()
            .build()
        )
        await host.start()
        client = host.services.get_service(ServiceDiscovery)
        registration = host.services.get_service(NacosRegistration)
        assert client.select_instance("yuanboot") == registration.instance
        watcher = client.watch_instances("yuanboot", interval=0.01)
        assert len(await anext(watcher)) == 1
        await watcher.aclose()
        await host.stop()
        assert not client.get_instances("yuanboot")

    asyncio.run(scenario())


def test_memory_selection_filters_disabled_and_unhealthy():
    client = MemoryDiscovery()
    try:
        client.register(ServiceInstance("a", "127.0.0.1", 8000))
        client.register(ServiceInstance("a", "127.0.0.2", 8000, healthy=False))
        client.register(ServiceInstance("a", "127.0.0.3", 8000, enabled=False))
        assert len(client.get_instances("a", healthy_only=False)) == 3
        assert len(client.get_instances("a")) == 1
        with pytest.raises(LookupError):
            client.select_instance("missing")
    finally:
        client.close()


@pytest.mark.parametrize("kind", ["consul", "eureka", "etcd"])
def test_registry_http_protocol_registration_query_heartbeat_and_cleanup(kind):
    requests = []
    instance = ServiceInstance("demo", "127.0.0.1", 8000, metadata={"lang": "python"})
    stored = {}

    def handler(request):
        requests.append(request)
        path = request.url.path
        payload = json.loads(request.content) if request.content else {}
        if kind == "consul":
            assert request.headers["X-Consul-Token"] == "test-token"
            if path.endswith("/register"):
                assert payload["Meta"] == instance.metadata
                assert payload["Check"]["TTL"] == "15s"
            if path.startswith("/v1/health/service/"):
                return httpx.Response(
                    200,
                    json=[
                        {
                            "Node": {"Address": "127.0.0.1"},
                            "Service": {
                                "Address": instance.ip,
                                "Port": 8000,
                                "Meta": instance.metadata,
                            },
                            "Checks": [{"Status": "passing"}],
                        }
                    ],
                )
        elif kind == "eureka":
            if request.method == "POST":
                assert payload["instance"]["leaseInfo"]["durationInSecs"] == 15
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "application": {
                            "instance": {
                                "ipAddr": instance.ip,
                                "port": {"$": 8000},
                                "status": "UP",
                                "metadata": instance.metadata,
                            }
                        }
                    },
                )
        elif kind == "etcd":
            if path.endswith("/grant"):
                return httpx.Response(200, json={"ID": "100"})
            if path.endswith("/put"):
                stored.update(payload)
                assert json.loads(base64.b64decode(payload["value"]))["metadata"] == {
                    "lang": "python"
                }
            if path.endswith("/range"):
                return httpx.Response(200, json={"kvs": [stored]})
            if path.endswith("/keepalive"):
                return httpx.Response(200, json={"result": {"TTL": "15", "ID": "100"}})
        return httpx.Response(200, json={})

    adapter = {"consul": ConsulClient, "eureka": EurekaClient, "etcd": EtcdClient}[kind]
    client = adapter(RegistryOptions(token="test-token"), transport=httpx.MockTransport(handler))
    try:
        client.register(instance)
        result = client.get_instances("demo")
        assert len(result) == 1
        assert result[0].metadata == {"lang": "python"}
        assert result[0].port == 8000
        client.heartbeat(instance)
        client.unregister(instance)
        assert any(request.method in {"DELETE", "PUT", "POST"} for request in requests)
    finally:
        client.close()
