import asyncio

import pytest

from yuanboot import ApplicationLife, BackgroundService, HostBuilder, HostedService


def test_events_services_and_reverse_shutdown():
    events = []

    class First(HostedService):
        async def start(self):
            events.append("first.start")

        async def stop(self):
            events.append("first.stop")

    class Second(HostedService):
        def start(self):
            events.append("second.start")

        def stop(self):
            events.append("second.stop")

    def life_events(life):
        for topic in ("starting", "started", "stopping", "stopped"):
            life.subscribe(topic, lambda event: events.append(event.topic))

    async def scenario():
        host = (
            HostBuilder()
            .configure_services(
                lambda services: services.add_hosted_service(First).add_hosted_service(Second)
            )
            .on_application_life_event(life_events)
            .build()
        )
        await host.start()
        assert host.life.state == "up"
        await host.stop()
        await host.stop()
        with pytest.raises(RuntimeError, match="once"):
            await host.start()

    asyncio.run(scenario())
    assert events == [
        "starting",
        "first.start",
        "second.start",
        "started",
        "stopping",
        "second.stop",
        "first.stop",
        "stopped",
    ]


def test_startup_failure_rolls_back_all_services():
    stopped = []

    class First(HostedService):
        async def stop(self):
            stopped.append("first")

    class Broken(HostedService):
        async def start(self):
            raise RuntimeError("start failed")

        async def stop(self):
            stopped.append("broken")
            raise RuntimeError("stop failed")

    async def scenario():
        host = (
            HostBuilder()
            .configure_services(lambda s: s.add_hosted_service(First).add_hosted_service(Broken))
            .build()
        )
        with pytest.raises(RuntimeError, match="start failed"):
            await host.start()
        assert stopped == ["broken", "first"]
        assert host.life.state == "down"

    asyncio.run(scenario())


def test_background_failure_and_console_stop_event():
    class BrokenWorker(BackgroundService):
        async def execute(self):
            raise RuntimeError("background failed")

    async def scenario():
        host = (
            HostBuilder().configure_services(lambda s: s.add_hosted_service(BrokenWorker)).build()
        )
        await host.start()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert host.life.state == "failed"
        with pytest.raises(ExceptionGroup):
            await host.stop()
        assert host.life.state == "down"

        event = asyncio.Event()
        event.set()
        host = HostBuilder().build()
        await host.run_async(event)
        assert host.life.state == "down"
        assert host.services._closed
        assert isinstance(host.life, ApplicationLife)

    asyncio.run(scenario())
