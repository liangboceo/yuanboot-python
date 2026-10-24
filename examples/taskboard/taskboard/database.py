import sqlite3
from pathlib import Path

from yuanboot import Configuration, HostedService


def database_path(configuration: Configuration) -> Path:
    return Path(configuration.get_string("database.path", "./data/taskboard.db")).expanduser()


class DatabaseInitializer(HostedService):
    def __init__(self, configuration: Configuration):
        self.configuration = configuration

    def start(self):
        path = database_path(self.configuration)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, timeout=10)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            with connection:
                connection.executescript("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 200),
                        description TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL CHECK(status IN ('todo', 'in_progress', 'done')),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS ix_tasks_status_created
                        ON tasks(status, created_at DESC);
                """)
        finally:
            connection.close()


class DatabaseSession:
    """One connection per request; FastAPI sync dependencies can run on different threads."""

    def __init__(self, configuration: Configuration):
        self.connection = sqlite3.connect(
            database_path(configuration), timeout=10, check_same_thread=False
        )
        self.connection.row_factory = sqlite3.Row

    def close(self):
        self.connection.close()
