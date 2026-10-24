"""Host-managed interval and second-resolution cron tasks (Go pkg/task)."""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from yuanboot.hosting import HostedService, invoke

logger = logging.getLogger("yuanboot.scheduler")


@dataclass
class Job:
    name: str
    callback: Callable
    interval: float | None = None
    cron: str | None = None
    timezone: str = "Asia/Shanghai"
    runs: int = 0
    failures: int = 0

    def delay(self):
        if self.interval is not None:
            return self.interval
        try:
            from croniter import croniter
        except ImportError as exc:
            raise ImportError('Cron requires: pip install "yuanboot[scheduler]"') from exc
        now = datetime.now(ZoneInfo(self.timezone))
        spec = self.cron
        # Go's five fields are second/minute/hour/day/month; optional sixth is weekday.
        if not spec.startswith("@") and len(spec.split()) == 5:
            spec += " *"
        return max(
            0,
            (
                croniter(spec, now, second_at_beginning=True).get_next(datetime) - now
            ).total_seconds(),
        )


class Scheduler(HostedService):
    """Jobs run serially per name. Multiple processes each execute their own schedule."""

    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._stop: asyncio.Event | None = None
        self._job_stops: dict[str, asyncio.Event] = {}

    def add(
        self, name: str, callback: Callable, *, interval=None, cron=None, timezone="Asia/Shanghai"
    ):
        if not name or name in self.jobs:
            raise ValueError("Job names must be nonempty and unique")
        if (interval is None) == (cron is None):
            raise ValueError("Specify one of interval or cron")
        if interval is not None and (not math.isfinite(interval) or interval <= 0):
            raise ValueError("Job interval must be finite and positive")
        job = Job(name, callback, interval, cron, timezone)
        job.delay()  # Validate the expression before starting the host.
        self.jobs[name] = job
        if self._stop is not None:
            self._job_stops[name] = asyncio.Event()
            self._tasks[name] = asyncio.create_task(self._run(job, self._job_stops[name]))
        return self

    async def _run(self, job, stop):
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=job.delay())
                return
            except TimeoutError:
                pass
            try:
                await invoke(job.callback)
                job.runs += 1
            except Exception:
                job.failures += 1
                logger.exception("Scheduled job failed: %s", job.name)

    async def start(self):
        self._stop = asyncio.Event()
        for name, job in self.jobs.items():
            self._job_stops[name] = asyncio.Event()
            self._tasks[name] = asyncio.create_task(
                self._run(job, self._job_stops[name]), name=f"schedule:{name}"
            )

    async def remove(self, name):
        task = self._tasks.pop(name, None)
        if task is not None:
            self._job_stops.pop(name).set()
            # A synchronous callback may be in a thread: let it finish before reusing the name.
            await task
        self.jobs.pop(name)

    async def stop(self):
        if self._stop is not None:
            self._stop.set()
            for event in self._job_stops.values():
                event.set()
            # Let in-flight jobs finish; idle timers wake immediately.
            await asyncio.gather(*self._tasks.values())
            self._tasks.clear()
            self._job_stops.clear()
            self._stop = None


def add_scheduler(services, configure=None):
    scheduler = Scheduler()
    if configure:
        configure(scheduler)
    services.add_hosted_service(Scheduler)
    services.add_singleton(Scheduler, instance=scheduler)
    return services
