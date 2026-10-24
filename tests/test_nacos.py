import asyncio
import json
from datetime import datetime

import httpx
import pytest

from yuanboot import Configuration, ConfigurationBuilder, HostBuilder, HostEnvironment
from yuanboot._version import __version__
from yuanboot.components.nacos import (
    NacosClient,
    NacosConfigurationSource,
    NacosError,
    NacosOptions,
    NacosRegistration,
    ServiceInstance,
)
from yuanboot.health import HealthRegistry
from yuanboot.hosting import ApplicationLife


def test_registration_matches_go_metadata_and_weight():
    configuration = Configuration(
        {
            "yuanboot": {
                "application": {"server": {"path": "/api", "port": 8080}},
                "cloud": {"discovery": {"ip": "127.0.0.1", "instance_metadata": {"region": 42}}},
            }
        }
    )
    client = NacosClient(NacosOptions(group="TEST", cluster="C1"))
    try:
        registration = NacosRegistration(
            client,
            configuration,
            HostEnvironment("sample", "prod", pid=123),
            ApplicationLife(),
            HealthRegistry(),
        )
        instance = registration.instance
        assert instance.weight == 10
        assert (instance.group, instance.cluster) == ("TEST", "C1")
        assert instance.healthy and instance.enabled and instance.ephemeral
        assert instance.metadata == {
            "yuanboot_version": __version__,
            "yuanboot_env": "prod",
            "yuanboot_author": "jackson",
            "yuanboot_application_description": "quickly,quickly,quickly,quickly,quickly!!!!!",
            "yuanboot_application_context-path": "/api",
            "yuanboot_application_pid": "123",
            "yuanboot_application_create_time": instance.metadata[
                "yuanboot_application_create_time"
            ],
            "yuanboot_application_name": "sample",
            "region": "42",
        }
        datetime.strptime(
            instance.metadata["yuanboot_application_create_time"], "%Y-%m-%d %H:%M:%S"
        )
    finally:
        client.close()


def test_auth_refresh_config_and_failover():
    calls = []
    tokens = []

    def transport(request):
        calls.append(request)
        if request.url.host == "offline":
            raise httpx.ConnectError("unreachable")
        if "login" in request.url.path:
            token = f"token-{len(tokens)}"
            tokens.append(token)
            return httpx.Response(200, json={"accessToken": token, "tokenTtl": 60})
        if request.url.params.get("accessToken") == "token-0":
            return httpx.Response(403)
        return httpx.Response(200, text="message: refreshed")

    client = NacosClient(
        NacosOptions(
            server_addr="http://offline:8848;http://online:8848",
            username="test",
            password="private",
        ),
        transport=httpx.MockTransport(transport),
    )
    try:
        assert client.get_config("demo.yml") == "message: refreshed"
        assert len(tokens) == 2
        assert all("private" not in str(request.url) for request in calls)
    finally:
        client.close()


def test_remote_reload_priority_and_bad_snapshot(monkeypatch):
    content = {"value": "feature:\n  message: remote\n  enabled: true\n"}

    def handler(request):
        return httpx.Response(200, text=content["value"])

    options = NacosOptions(data_id="demo.yml", poll_interval=0.01)
    client = NacosClient(options, transport=httpx.MockTransport(handler))
    source = NacosConfigurationSource(options, client=client)
    monkeypatch.setenv("YUANBOOT_FEATURE__MESSAGE", "environment")
    config = (
        ConfigurationBuilder()
        .add_defaults({"feature": {"message": "local", "other": 1}})
        .add_source(source)
        .add_environment()
        .build()
    )
    try:
        assert config.get_string("feature.message") == "environment"
        assert config.get_bool("feature.enabled")
        assert config.get_int("feature.other") == 1
        content["value"] = "feature:\n  message: second\n  enabled: false\n"
        assert config.reload()
        assert not config.get_bool("feature.enabled")
        assert config.version == 1
        content["value"] = "- invalid-mapping"
        with pytest.raises(ValueError, match="mapping"):
            config.reload()
        assert not config.get_bool("feature.enabled") and config.version == 1
    finally:
        config.close()
        client.close()


def test_configuration_monitor_refresh_and_shutdown():
    class Source:
        poll_interval = 0.01
        value = 1
        closed = False

        def load(self):
            return {"version": self.value}

        def close(self):
            self.closed = True

    async def scenario():
        source = Source()
        config = ConfigurationBuilder().add_source(source).build()
        changed = asyncio.Event()

        async def callback(event):
            changed.set()

        host = (
            HostBuilder(config)
            .on_application_life_event(
                lambda life: life.subscribe("configuration_changed", callback)
            )
            .build()
        )
        await host.start()
        source.value = 2
        await asyncio.wait_for(changed.wait(), timeout=1)
        assert config.get_int("version") == 2
        await host.stop()
        assert source.closed

    asyncio.run(scenario())


def test_naming_payload_and_round_robin():
    def handler(request):
        if request.url.path.endswith("/list"):
            return httpx.Response(
                200,
                json={
                    "hosts": [
                        {"ip": "127.0.0.1", "port": 8000, "healthy": True, "weight": 1},
                        {"ip": "127.0.0.2", "port": 8000, "healthy": True, "weight": 1},
                        {"ip": "127.0.0.3", "port": 8000, "healthy": False},
                    ]
                },
            )
        if request.url.path.endswith("/beat"):
            return httpx.Response(200, json={"code": 10200, "clientBeatInterval": 5000})
        return httpx.Response(200, text="ok")

    client = NacosClient(NacosOptions(), transport=httpx.MockTransport(handler))
    instance = ServiceInstance("test", "127.0.0.1", 8000)
    try:
        client.register(instance)
        assert client.heartbeat(instance)["code"] == 10200
        assert len(client.get_instances("test")) == 2
        assert client.select_instance("test").ip == "127.0.0.1"
        assert client.select_instance("test").ip == "127.0.0.2"
        client.unregister(instance)
    finally:
        client.close()


def test_error_never_exposes_response_tokens():
    def handler(request):
        return httpx.Response(401, json={"password": "private", "accessToken": "private"})

    client = NacosClient(NacosOptions(), transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(NacosError) as error:
            client.get_config("demo")
        assert "private" not in str(error.value)
        assert error.value.status_code == 401
    finally:
        client.close()


def test_json_source_and_optional_missing():
    options = NacosOptions(data_id="demo.json", format="json")
    client = NacosClient(
        options,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, text=json.dumps({"answer": 42}))
        ),
    )
    try:
        assert NacosConfigurationSource(options, client=client).load() == {"answer": 42}
    finally:
        client.close()
    client = NacosClient(
        options, transport=httpx.MockTransport(lambda request: httpx.Response(404))
    )
    try:
        assert NacosConfigurationSource(options, optional=True, client=client).load() == {}
    finally:
        client.close()
