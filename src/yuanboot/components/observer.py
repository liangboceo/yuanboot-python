"""In-process async broadcast, corresponding to Go pkg/mq/observer (not a broker)."""

from __future__ import annotations

import asyncio

_CLOSED = object()


class Subscription:
    def __init__(self, observer, capacity):
        self._observer = observer
        self._queue = asyncio.Queue(capacity)
        self._closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._closed and self._queue.empty():
            raise StopAsyncIteration
        value = await self._queue.get()
        if value is _CLOSED:
            raise StopAsyncIteration
        return value

    def close(self):
        if not self._closed:
            self._closed = True
            self._observer._listeners.discard(self)
            if self._queue.full():
                self._queue.get_nowait()
            self._queue.put_nowait(_CLOSED)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.close()


class Observer:
    """Use from a single event loop. Full listeners raise QueueFull; no silent message drops."""

    def __init__(self):
        self._listeners: set[Subscription] = set()
        self._closed = False

    def subscribe(self, *, capacity=100):
        if self._closed:
            raise RuntimeError("Observer is closed")
        if capacity < 1:
            raise ValueError("Subscription capacity must be positive")
        subscription = Subscription(self, capacity)
        self._listeners.add(subscription)
        return subscription

    def publish(self, value):
        if self._closed:
            raise RuntimeError("Observer is closed")
        if any(listener._queue.full() for listener in self._listeners):
            raise asyncio.QueueFull
        for listener in self._listeners:
            listener._queue.put_nowait(value)

    def close(self):
        self._closed = True
        for listener in tuple(self._listeners):
            listener.close()
