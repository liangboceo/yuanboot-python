import asyncio
import logging

from yuanboot import BackgroundService


class Worker(BackgroundService):
    async def execute(self):
        try:
            while True:
                logging.getLogger(__name__).info("__PROJECT__ is running")
                await asyncio.sleep(5)
        finally:
            logging.getLogger(__name__).info("__PROJECT__ stopped")
