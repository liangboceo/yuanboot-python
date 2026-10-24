import asyncio
import logging

from yuanboot.configuration import Configuration
from yuanboot.health import HealthRegistry
from yuanboot.hosting import ApplicationLife, BackgroundService, invoke

logger = logging.getLogger("yuanboot.configuration")


class ConfigurationMonitor(BackgroundService):
    def __init__(self, configuration: Configuration, life: ApplicationLife, health: HealthRegistry):
        super().__init__(life)
        self.configuration = configuration
        health.add("configuration", lambda: configuration.last_refresh_error is None)

    async def start(self):
        if self.configuration.poll_interval is not None:
            await super().start()

    async def execute(self):
        while True:
            await asyncio.sleep(self.configuration.poll_interval)
            try:
                if await invoke(self.configuration.reload):
                    await self.life.publish("configuration_changed", self.configuration)
                    logger.info(
                        "Remote configuration refreshed; version=%s", self.configuration.version
                    )
            except Exception as exc:
                self.configuration.last_refresh_error = type(exc).__name__
                logger.warning("Remote configuration refresh failed; retaining last good snapshot")

    async def stop(self):
        try:
            await super().stop()
        finally:
            await invoke(self.configuration.close)
