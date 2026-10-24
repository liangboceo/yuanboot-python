from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import URL
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import Session, sessionmaker
except ImportError as exc:
    raise ImportError('MySQL requires: pip install "yuanboot[mysql]"') from exc

from yuanboot.configuration import Configuration
from yuanboot.health import HealthRegistry
from yuanboot.hosting import HostedService


class MySqlOptions(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=3306, ge=1, le=65535)
    database: str = ""
    username: str = "root"
    password: SecretStr = SecretStr("")
    url: SecretStr | None = None
    charset: str = "utf8mb4"
    pool_size: int = Field(default=5, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    pool_timeout: float = Field(default=30, gt=0)
    pool_recycle: int = Field(default=1800, ge=-1)
    connect_timeout: int = Field(default=5, ge=1)
    read_timeout: int = Field(default=10, ge=1)
    write_timeout: int = Field(default=10, ge=1)
    check_on_start: bool = True

    @classmethod
    def from_configuration(cls, configuration: Configuration):
        values = configuration.get("yuanboot.datasource.mysql")
        if values is None:
            values = configuration.get("yuanboot.datasource.db", {})
        values = dict(values)
        if values.get("max_open_conns", 0) > 0:
            maximum = values["max_open_conns"]
            idle = max(1, min(values.get("max_idle_conns", maximum), maximum))
            values.setdefault("pool_size", idle)
            values.setdefault("max_overflow", max(0, maximum - values["pool_size"]))
        if "conn_max_lifetime" in values:
            values.setdefault("pool_recycle", values["conn_max_lifetime"])
        # Accept the Go datasource's tcp(host:port)/database?charset=... form.
        raw = values.get("url", "")
        if raw.startswith("tcp("):
            from urllib.parse import parse_qs

            authority, database = raw[4:].split(")/", 1)
            host, port = authority.rsplit(":", 1)
            name, _, query = database.partition("?")
            values.update(
                host=host,
                port=int(port),
                database=name,
                charset=parse_qs(query).get("charset", ["utf8mb4"])[0],
            )
            values.pop("url")
        return cls.model_validate(values)


class MySqlDataSource:
    def __init__(self, configuration: Configuration):
        self.options = MySqlOptions.from_configuration(configuration)
        options = self.options
        url = (
            options.url.get_secret_value()
            if options.url
            else URL.create(
                "mysql+pymysql",
                username=options.username,
                password=options.password.get_secret_value(),
                host=options.host,
                port=options.port,
                database=options.database or None,
                query={"charset": options.charset},
            )
        )
        if options.url and not str(url).startswith("mysql+pymysql://"):
            raise ValueError("MySQL URL must use mysql+pymysql://")
        self.engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=options.pool_size,
            max_overflow=options.max_overflow,
            pool_timeout=options.pool_timeout,
            pool_recycle=options.pool_recycle,
            hide_parameters=True,
            connect_args={
                "connect_timeout": options.connect_timeout,
                "read_timeout": options.read_timeout,
                "write_timeout": options.write_timeout,
            },
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def connect(self):
        return self.engine.connect()

    def transaction(self):
        """Context manager: commit on success, roll back on exception."""
        return self.engine.begin()

    def ping(self) -> bool:
        try:
            with self.connect() as connection:
                return connection.execute(text("SELECT 1")).scalar_one() == 1
        except SQLAlchemyError:
            return False

    def close(self):
        self.engine.dispose()


class MySqlLifecycle(HostedService):
    def __init__(self, source: MySqlDataSource, health: HealthRegistry):
        self.source = source
        health.add("mysql", source.ping)

    def start(self):
        if self.source.options.check_on_start and not self.source.ping():
            raise RuntimeError("MySQL startup health check failed")


def add_mysql(services):
    def session(source: MySqlDataSource) -> Session:
        return source.session_factory()

    services.add_singleton(MySqlDataSource)
    services.add_scoped(Session, session)
    services.add_hosted_service(MySqlLifecycle)
    return services
