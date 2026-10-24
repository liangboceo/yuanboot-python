import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from taskboard.main import create_app

from yuanboot import Configuration


@pytest.fixture
def configuration(tmp_path):
    if os.environ.get("TASKBOARD_TEST_CLOUD") == "1":
        from sqlalchemy import text

        from yuanboot.components.mysql import MySqlDataSource
        from yuanboot.components.redis import RedisDataSource

        schema = "yuanboot_business_it_" + uuid4().hex[:12]
        mysql = {
            "host": os.environ["MYSQL_HOST"],
            "port": int(os.environ.get("MYSQL_PORT", 3306)),
            "username": os.environ["MYSQL_USERNAME"],
            "password": os.environ["MYSQL_PASSWORD"],
        }
        admin = MySqlDataSource(Configuration({"yuanboot": {"datasource": {"mysql": mysql}}}))
        prefix = schema + ":"
        config = Configuration(
            {
                "yuanboot": {
                    "application": {"name": "taskboard-test"},
                    "datasource": {
                        "mysql": {**mysql, "database": schema},
                        "redis": {
                            "url": os.environ["REDIS_URL"],
                            "password": os.environ["REDIS_PASSWORD"],
                            "prefix": prefix,
                        },
                    },
                }
            }
        )
        with admin.transaction() as connection:
            connection.execute(text(f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4"))
        try:
            yield config
        finally:
            redis = RedisDataSource(config)
            try:
                for key in redis.client.scan_iter(match=prefix + "*"):
                    redis.client.delete(key)
            finally:
                redis.close()
                with admin.transaction() as connection:
                    connection.execute(text(f"DROP DATABASE `{schema}`"))
                admin.close()
        return
    yield Configuration(
        {
            "yuanboot": {"application": {"name": "taskboard-test"}},
            "database": {"path": str(tmp_path / "tasks.db")},
        }
    )


@pytest.fixture
def client(configuration):
    with TestClient(create_app(configuration)) as test_client:
        yield test_client
