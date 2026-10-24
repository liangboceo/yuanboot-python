from __future__ import annotations

import json

from pydantic import BaseModel, Field, SecretStr

try:
    import redis
except ImportError as exc:
    raise ImportError('Redis requires: pip install "yuanboot[redis]"') from exc

from yuanboot.configuration import Configuration
from yuanboot.health import HealthRegistry
from yuanboot.hosting import HostedService


class RedisOptions(BaseModel):
    url: SecretStr = SecretStr("redis://127.0.0.1:6379")
    username: str | None = None
    password: SecretStr | None = None
    db: int = Field(default=0, ge=0)
    prefix: str = "yuanboot:"
    pool_size: int = Field(default=10, ge=1)
    dial_timeout: float = Field(default=5, gt=0)
    read_timeout: float = Field(default=3, gt=0)
    cluster: bool = False
    check_on_start: bool = True


class RedisDataSource:
    def __init__(self, configuration: Configuration):
        self.options = RedisOptions.model_validate(
            configuration.get("yuanboot.datasource.redis", {})
        )
        options = self.options
        url = options.url.get_secret_value()
        if "://" not in url:
            url = "redis://" + url
        kwargs = dict(
            decode_responses=True,
            max_connections=options.pool_size,
            socket_connect_timeout=options.dial_timeout,
            socket_timeout=options.read_timeout,
        )
        if options.username is not None:
            kwargs["username"] = options.username
        if options.password is not None:
            kwargs["password"] = options.password.get_secret_value()
        if options.cluster:
            if options.db != 0:
                raise ValueError("Redis Cluster supports db=0 only")
            self.client = redis.RedisCluster.from_url(url, **kwargs)
        else:
            self.client = redis.Redis.from_url(url, db=options.db, **kwargs)

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except redis.RedisError:
            return False

    def close(self):
        self.client.close()


class RedisCache:
    def __init__(self, source: RedisDataSource):
        self.client = source.client
        self.prefix = source.options.prefix

    def get_json(self, key: str, default=None):
        value = self.client.get(self.prefix + key)
        return json.loads(value) if value is not None else default

    def set_json(self, key: str, value, *, ttl: int | None = None) -> bool:
        if ttl is not None and ttl < 1:
            raise ValueError("Cache TTL must be positive")
        return bool(
            self.client.set(self.prefix + key, json.dumps(value, ensure_ascii=False), ex=ttl)
        )

    def delete(self, key: str) -> bool:
        return bool(self.client.delete(self.prefix + key))

    def lock(self, name: str, *, timeout: float = 30, blocking_timeout: float = 5):
        if timeout <= 0 or blocking_timeout < 0:
            raise ValueError("Lock timeout must be positive and blocking_timeout non-negative")
        return self.client.lock(
            self.prefix + "lock:" + name, timeout=timeout, blocking_timeout=blocking_timeout
        )


class RedisLifecycle(HostedService):
    def __init__(self, source: RedisDataSource, health: HealthRegistry):
        self.source = source
        health.add("redis", source.ping)

    def start(self):
        if self.source.options.check_on_start and not self.source.ping():
            raise RuntimeError("Redis startup health check failed")


def add_redis(services):
    services.add_singleton(RedisDataSource)
    services.add_singleton(RedisCache)
    services.add_hosted_service(RedisLifecycle)
    return services
