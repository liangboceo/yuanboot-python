"""Prepare the dedicated demo database and Nacos document. Never overwrites an existing document."""

import os
from pathlib import Path

from yuanboot import Configuration
from yuanboot.components.mysql import MySqlDataSource
from yuanboot.components.nacos import NacosClient, NacosError, NacosOptions


def main():
    source = MySqlDataSource(
        Configuration(
            {
                "yuanboot": {
                    "datasource": {
                        "mysql": {
                            "host": os.environ["MYSQL_HOST"],
                            "port": int(os.environ.get("MYSQL_PORT", 3306)),
                            "username": os.environ["MYSQL_USERNAME"],
                            "password": os.environ["MYSQL_PASSWORD"],
                        }
                    }
                }
            }
        )
    )
    try:
        with source.transaction() as connection:
            connection.exec_driver_sql(
                "CREATE DATABASE IF NOT EXISTS `yuanboot_python_taskboard` CHARACTER SET utf8mb4"
            )
    finally:
        source.close()
    options = NacosOptions(
        server_addr=os.environ["NACOS_SERVER_ADDR"],
        username=os.environ["NACOS_USERNAME"],
        password=os.environ["NACOS_PASSWORD"],
        group="YUANBOOT_PYTHON_DEMO",
    )
    client = NacosClient(options)
    data_id = "yuanboot-python-taskboard.yml"
    try:
        try:
            client.get_config(data_id)
            print("Existing demo configuration preserved")
        except NacosError as exc:
            if exc.status_code != 404:
                raise
            content = (
                Path(__file__).resolve().parent.parent
                / "examples/taskboard/nacos-config.example.yml"
            ).read_text()
            if not client.publish_config(data_id, content):
                raise RuntimeError("Could not publish demo configuration") from None
            print("Demo Nacos configuration published")
    finally:
        client.close()
    print("Dedicated MySQL schema ready: yuanboot_python_taskboard")


if __name__ == "__main__":
    main()
