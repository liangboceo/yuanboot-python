"""Expiring, one-use captcha and session storage, shared through Redis when configured."""

import json
import threading
import time

from yuanboot import Configuration, ServiceProvider
from yuanboot.components.redis import RedisDataSource


class Cache:
    def __init__(self, configuration: Configuration, provider: ServiceProvider):
        self.client = None
        self.prefix = configuration.get_string("admin.cache_prefix", "__PROJECT__:")
        self.values = {}
        self.lock = threading.RLock()
        if configuration.get("yuanboot.datasource.redis") is not None:
            self.client = provider.get_service(RedisDataSource).client

    def get(self, key):
        if self.client:
            raw = self.client.get(self.prefix + key)
            return json.loads(raw) if raw is not None else None
        with self.lock:
            value, expiry = self.values.get(key, (None, 0))
            if expiry > time.monotonic():
                return value
            self.values.pop(key, None)
            return None

    def put(self, key, value, ttl):
        if self.client:
            self.client.set(self.prefix + key, json.dumps(value), ex=ttl)
        else:
            with self.lock:
                if len(self.values) >= 10000:
                    now = time.monotonic()
                    self.values = {k: v for k, v in self.values.items() if v[1] > now}
                    if len(self.values) >= 10000:
                        raise ValueError("会话容量已满，请稍后重试")
                self.values[key] = (value, time.monotonic() + ttl)

    def consume(self, key):
        if self.client:
            raw = self.client.eval(
                "local v=redis.call('GET',KEYS[1]); "
                "if v then redis.call('DEL',KEYS[1]) end; return v",
                1,
                self.prefix + key,
            )
            return json.loads(raw) if raw is not None else None
        with self.lock:
            value = self.get(key)
            self.values.pop(key, None)
            return value

    def delete(self, key):
        if self.client:
            self.client.delete(self.prefix + key)
        else:
            with self.lock:
                self.values.pop(key, None)

    def increment(self, key, ttl):
        if self.client:
            script = (
                "local n=redis.call('INCR',KEYS[1]); "
                "if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n"
            )
            return int(self.client.eval(script, 1, self.prefix + key, ttl))
        with self.lock:
            value = (self.get(key) or 0) + 1
            expiry = self.values.get(key, (None, time.monotonic() + ttl))[1]
            self.values[key] = (value, expiry)
            return value
