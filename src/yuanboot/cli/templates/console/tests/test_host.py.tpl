import asyncio

from __PACKAGE__.main import create_host


def test_console_lifecycle():
    async def scenario():
        host = create_host()
        await host.start()
        assert host.life.state == "up"
        await asyncio.sleep(0)
        await host.stop()
        assert host.life.state == "down"

    asyncio.run(scenario())
