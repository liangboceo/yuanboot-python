import asyncio
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import BaseModel

from yuanboot import ConfigurationBuilder, HostBuilder
from yuanboot.components.apollo import ApolloConfigurationSource, ApolloOptions
from yuanboot.components.email import SmtpClient, SmtpOptions
from yuanboot.components.httpclient import HttpClient
from yuanboot.components.nacos import ServiceInstance
from yuanboot.components.observer import Observer
from yuanboot.components.scheduler import Job, Scheduler


def test_http_discovery_reresolves_and_preserves_request():
    discovery = MagicMock()
    discovery.select_instance.side_effect = [
        ServiceInstance(
            "orders", "127.0.0.1", port, metadata={"yuanboot_application_context-path": "/api"}
        )
        for port in (8080, 8081)
    ]
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    client = HttpClient(
        "lb://orders/v1", discovery=discovery, transport=httpx.MockTransport(handler)
    )
    try:
        assert client.get("items", params={"q": "测试"}).json() == {"ok": True}
        client.post("items", json={"id": 1})
        assert [request.url.port for request in requests] == [8080, 8081]
        assert requests[0].url.path == "/api/v1/items"
        assert requests[0].url.params["q"] == "测试"
        assert requests[1].method == "POST"
        with pytest.raises(ValueError):
            client.get("https://another.example/")
    finally:
        client.close()


def test_apollo_signed_polling_and_options_snapshot():
    state = {"value": "first"}

    def handler(request):
        assert request.url.path == "/configs/demo/default/application"
        assert request.headers["Authorization"].startswith("Apollo demo:")
        return httpx.Response(200, json={"configurations": {"feature.message": state["value"]}})

    source = ApolloConfigurationSource(
        ApolloOptions(appid="demo", secret="test"), transport=httpx.MockTransport(handler)
    )
    configuration = ConfigurationBuilder().add_source(source).build()

    class Feature(BaseModel):
        message: str

    snapshot = configuration.options(Feature, "feature")
    assert snapshot.current_value.message == "first"
    state["value"] = "updated"
    assert configuration.reload()
    assert snapshot.current_value.message == "updated"
    configuration.close()
    with pytest.raises(RuntimeError):
        configuration.reload()


def test_scheduler_failure_isolation_serial_execution_and_stop():
    async def scenario():
        completed = asyncio.Event()
        count = 0

        async def callback():
            nonlocal count
            count += 1
            if count == 1:
                raise ValueError("expected failure")
            completed.set()

        host = (
            HostBuilder()
            .use_scheduler(lambda scheduler: scheduler.add("probe", callback, interval=0.01))
            .build()
        )
        await host.start()
        await asyncio.wait_for(completed.wait(), 2)
        scheduler = host.services.get_service(Scheduler)
        assert scheduler.jobs["probe"].failures == 1
        await host.stop()
        assert not scheduler._tasks
        stopped = count
        await asyncio.sleep(0.03)
        assert count == stopped

    asyncio.run(scenario())
    assert 0 <= Job("cron", lambda: None, cron="*/5 * * * * *").delay() <= 5
    with pytest.raises(ValueError):
        Scheduler().add("invalid", lambda: None, interval=0)


def test_observer_broadcast_backpressure_and_shutdown():
    async def scenario():
        observer = Observer()
        first = observer.subscribe(capacity=1)
        second = observer.subscribe(capacity=1)
        observer.publish({"id": 1})
        with pytest.raises(asyncio.QueueFull):
            observer.publish({"id": 2})
        assert await anext(first) == {"id": 1}
        assert await anext(second) == {"id": 1}
        first.close()
        observer.publish({"id": 3})
        assert await anext(second) == {"id": 3}
        observer.close()
        with pytest.raises(StopAsyncIteration):
            await anext(second)

    asyncio.run(scenario())


def test_smtp_tls_and_mime_without_sending_mail():
    with patch("yuanboot.components.email.smtplib.SMTP") as factory:
        smtp = factory.return_value.__enter__.return_value
        smtp.send_message.return_value = {}
        SmtpClient(SmtpOptions(username="test", password="secret")).send(
            "sender@example.com",
            "a@example.com;b@example.com",
            "中文标题",
            "<b>内容</b>",
            html=True,
            attachments={"test.txt": b"example"},
        )
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("test", "secret")
        message = smtp.send_message.call_args.args[0]
        assert message["Subject"] == "中文标题"
        assert len(list(message.iter_attachments())) == 1
