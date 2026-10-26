"""Administration database using the framework MySQL source or local SQLite."""

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from yuanboot import Configuration, ServiceProvider
from yuanboot.components.mysql import MySqlDataSource
from yuanboot.health import HealthRegistry
from yuanboot.hosting import HostedService

from .models import Base


class Database:
    def __init__(
        self, configuration: Configuration, provider: ServiceProvider, health: HealthRegistry
    ):
        self.owned = configuration.get("yuanboot.datasource.mysql") is None
        if not self.owned:
            self.engine = provider.get_service(MySqlDataSource).engine
        else:
            url = configuration.get_string("admin.database_url", "sqlite:///./data/admin.db")
            if not url.startswith("sqlite:///"):
                raise ValueError("Configure MySQL through yuanboot.datasource.mysql")
            filename = url.removeprefix("sqlite:///")
            if not Path(filename).is_absolute() and filename != ":memory:":
                filename = str(Path(__file__).resolve().parents[1] / filename)
                url = "sqlite:///" + filename
            if filename != ":memory:":
                Path(filename).parent.mkdir(parents=True, exist_ok=True)
            self.engine = create_engine(
                url, connect_args={"check_same_thread": False, "timeout": 15}
            )
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        health.add("admin-database", self.ping)

    def ping(self):
        with self.engine.connect() as connection:
            return connection.execute(text("SELECT 1")).scalar_one() == 1

    def close(self):
        if self.owned:
            self.engine.dispose()


class DatabaseLifecycle(HostedService):
    def __init__(self, database: Database):
        self.database = database

    def start(self):
        Base.metadata.create_all(self.database.engine)
