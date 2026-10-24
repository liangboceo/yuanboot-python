import asyncio
import logging

from yuanboot import BackgroundService

logger = logging.getLogger(__name__)


class HeartbeatWorker(BackgroundService):
    async def execute(self):
        try:
            while True:
                logger.info("__PROJECT__ worker heartbeat")
                await asyncio.sleep(30)
        finally:
            logger.info("__PROJECT__ worker stopped")
