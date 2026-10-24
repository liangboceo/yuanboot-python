"""Live integration verification; credentials come only from environment variables.

Creates an isolated MySQL schema, Redis prefix, Nacos data ID/service, then removes them.
Run after loading .env.integration and installing yuanboot[dev,all].
"""

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from yuanboot import Configuration, ConfigurationBuilder, HostBuilder
from yuanboot.components.mysql import MySqlDataSource
from yuanboot.components.nacos import NacosClient, NacosOptions, NacosRegistration
from yuanboot.components.redis import RedisCache, RedisDataSource
from yuanboot.health import HealthRegistry


async def eventually(callback, *, seconds=12):
    async with asyncio.timeout(seconds):
        while not await asyncio.to_thread(callback):  # noqa: ASYNC110 - poll external Nacos state
            await asyncio.sleep(0.1)


async def verify():
    run_id = "yuanboot_py_it_" + uuid4().hex[:12]
    schema = run_id
    prefix = run_id + ":"
    data_id = run_id + ".yml"
    group = "YUANBOOT_PYTHON_TEST"
    nacos = NacosOptions(
        server_addr=os.environ["NACOS_SERVER_ADDR"],
        username=os.environ["NACOS_USERNAME"],
        password=os.environ["NACOS_PASSWORD"],
        group=group,
        data_id=data_id,
        poll_interval=0.2,
    )
    mysql = {
        "host": os.environ["MYSQL_HOST"],
        "port": int(os.environ.get("MYSQL_PORT", 3306)),
        "username": os.environ["MYSQL_USERNAME"],
        "password": os.environ["MYSQL_PASSWORD"],
    }
    admin = MySqlDataSource(Configuration({"yuanboot": {"datasource": {"mysql": mysql}}}))
    client = NacosClient(nacos)
    host = None
    schema_created = config_published = False
    report = {"started_at": datetime.now(UTC).isoformat(), "run_id": run_id, "checks": {}}
    cleanup_errors = []
    try:
        client.login()
        assert client.ping()
        report["checks"]["nacos_authentication"] = "passed"
        with admin.transaction() as connection:
            connection.exec_driver_sql(f"CREATE DATABASE `{schema}` CHARACTER SET utf8mb4")
        schema_created = True
        assert client.publish_config(data_id, "demo:\n  message: initial\n  removed: old\n")
        config_published = True
        local = {
            "yuanboot": {
                "application": {"name": run_id, "server": {"address": ":18080"}},
                "logging": {"console": False, "json": True, "file": "reports/components.log"},
                "datasource": {
                    "mysql": {**mysql, "database": schema},
                    "redis": {
                        "url": os.environ["REDIS_URL"],
                        "password": os.environ["REDIS_PASSWORD"],
                        "prefix": prefix,
                    },
                },
                "cloud": {
                    "nacos": nacos.model_dump(mode="python"),
                    "discovery": {
                        "type": "nacos",
                        "ip": "127.0.0.1",
                        "port": 18080,
                        "heartbeat_interval": 0.5,
                        "instance_metadata": {"integration_run": run_id},
                    },
                },
            }
        }
        # Never serialize SecretStr back into bootstrap config as its masked representation.
        local["yuanboot"]["cloud"]["nacos"]["password"] = nacos.password.get_secret_value()
        configuration = ConfigurationBuilder().add_defaults(local).add_nacos(nacos).build()
        assert configuration.get_string("demo.message") == "initial"
        report["checks"]["nacos_configuration_load"] = "passed"
        changed = asyncio.Event()

        async def on_change(event):
            changed.set()

        host = (
            HostBuilder(configuration)
            .use_components()
            .on_application_life_event(
                lambda life: life.subscribe("configuration_changed", on_change)
            )
            .build()
        )
        await host.start()
        source = host.services.get_service(MySqlDataSource)
        with source.transaction() as connection:
            connection.execute(text("CREATE TABLE probe (id INT PRIMARY KEY, value VARCHAR(200))"))
            connection.execute(
                text("INSERT INTO probe VALUES (:id, :value)"), {"id": 1, "value": "提交成功"}
            )
        try:
            with source.transaction() as connection:
                connection.execute(text("INSERT INTO probe VALUES (2, 'rollback')"))
                raise ValueError("intentional rollback")
        except ValueError:
            pass
        async with host.services.create_scope() as scope:
            session = scope.get_service(Session)
            assert session.execute(text("SELECT count(*) FROM probe")).scalar_one() == 1
            assert (
                session.execute(text("SELECT value FROM probe WHERE id=1")).scalar_one()
                == "提交成功"
            )
        report["checks"]["mysql_pool_commit_rollback_and_scoped_session"] = "passed"
        cache = host.services.get_service(RedisCache)
        assert cache.set_json("probe", {"hello": "世界"}, ttl=30)
        assert cache.get_json("probe") == {"hello": "世界"}
        assert cache.client.ttl(prefix + "probe") > 0
        lock = cache.lock("exclusive", timeout=10, blocking_timeout=0)
        assert lock.acquire(blocking=False)
        try:
            contender = cache.lock("exclusive", timeout=10, blocking_timeout=0)
            assert not contender.acquire(blocking=False)
        finally:
            lock.release()
        assert cache.delete("probe")
        assert cache.get_json("probe") is None
        report["checks"]["redis_json_ttl_lock_and_delete"] = "passed"
        registration = host.services.get_service(NacosRegistration)
        await eventually(lambda: len(client.get_instances(run_id)) == 1)
        assert client.select_instance(run_id).metadata["integration_run"] == run_id
        remote_instance = client.select_instance(run_id)
        assert remote_instance.weight == 10
        assert remote_instance.metadata == registration.instance.metadata
        assert set(remote_instance.metadata) >= {
            "yuanboot_version",
            "yuanboot_env",
            "yuanboot_author",
            "yuanboot_application_description",
            "yuanboot_application_context-path",
            "yuanboot_application_pid",
            "yuanboot_application_create_time",
            "yuanboot_application_name",
        }
        report["checks"]["nacos_go_metadata_parity"] = "passed"
        assert client.heartbeat(registration.instance).get("code", 10200) == 10200
        report["checks"]["nacos_registration_discovery_and_heartbeat"] = "passed"
        assert client.publish_config(data_id, "demo:\n  message: updated\n")
        await asyncio.wait_for(changed.wait(), timeout=12)
        assert configuration.get_string("demo.message") == "updated"
        assert configuration.get("demo.removed") is None
        report["checks"]["nacos_configuration_hot_reload"] = "passed"
        checks = host.services.get_service(HealthRegistry).checks()
        assert all(await asyncio.gather(*(asyncio.to_thread(check) for check in checks.values())))
        report["checks"]["component_health_registry"] = "passed"
        await host.stop()
        await eventually(lambda: not client.get_instances(run_id))
        report["checks"]["nacos_graceful_deregistration"] = "passed"
        report["checks"]["logging_json_file"] = (
            "passed" if await asyncio.to_thread(Path("reports/components.log").exists) else "failed"
        )
    finally:
        if host is not None:
            try:
                # Remove only keys in this integration run's unique prefix.
                if host._phase != "stopped":
                    redis_source = host.services.get_service(RedisDataSource)
                    for key in redis_source.client.scan_iter(match=prefix + "*"):
                        redis_source.client.delete(key)
                await host.stop()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        for action in (
            lambda: client.delete_service(run_id) if host else None,
            lambda: client.delete_config(data_id) if config_published else None,
        ):
            try:
                action()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        if schema_created:
            try:
                with admin.transaction() as connection:
                    connection.exec_driver_sql(f"DROP DATABASE `{schema}`")
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        admin.close()
        client.close()
        report["cleanup"] = "passed" if not cleanup_errors else cleanup_errors
        report["finished_at"] = datetime.now(UTC).isoformat()
        await asyncio.to_thread(Path("reports").mkdir, exist_ok=True)
        await asyncio.to_thread(
            Path("reports/components-integration.json").write_text,
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        )
    assert not cleanup_errors, f"Integration cleanup failed: {cleanup_errors}"
    return report


if __name__ == "__main__":
    print(json.dumps(asyncio.run(verify()), ensure_ascii=False, indent=2))
