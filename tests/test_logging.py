import json
import logging

from fastapi.testclient import TestClient

from yuanboot import Configuration
from yuanboot.logging import get_logger
from yuanboot.web import WebHostBuilder


def test_json_request_context_redaction_and_shutdown(tmp_path):
    path = tmp_path / "app.log"
    config = Configuration(
        {
            "yuanboot": {
                "application": {"name": "log-test"},
                "logging": {"json": True, "console": False, "file": str(path)},
            }
        }
    )

    def endpoints(router):
        @router.get("/log")
        def log():
            get_logger("business").info(
                "operation completed", extra={"payload": {"password": "hidden", "name": "visible"}}
            )
            return {"ok": True}

    logger = logging.getLogger("yuanboot")
    original_handlers = list(logger.handlers)
    host = (
        WebHostBuilder(config)
        .use_logging()
        .configure(lambda app: app.use_endpoints(endpoints))
        .build()
    )
    with TestClient(host) as client:
        response = client.get("/log", headers={"X-Request-ID": "correlation-42"})
        assert response.status_code == 200
    records = [json.loads(line) for line in path.read_text().splitlines()]
    business = next(record for record in records if record["message"] == "operation completed")
    assert business["request_id"] == "correlation-42"
    assert business["app"] == "log-test"
    assert business["extra"]["payload"] == {"password": "***", "name": "visible"}
    assert logger.handlers == original_handlers


def test_file_rotation(tmp_path):
    from yuanboot.logging import LoggingManager

    path = tmp_path / "rotated.log"
    manager = LoggingManager(
        Configuration(
            {
                "yuanboot": {
                    "logging": {
                        "console": False,
                        "file": str(path),
                        "max_bytes": 150,
                        "backup_count": 2,
                    }
                }
            }
        )
    )
    try:
        for _ in range(10):
            manager.get_logger("test").info("A message long enough to cause rotation")
    finally:
        manager.close()
    assert path.exists() and path.with_name("rotated.log.1").exists()
    assert len(list(tmp_path.glob("rotated.log*"))) <= 3
