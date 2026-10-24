"""Application logging with request correlation, JSON and rotating files."""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from pydantic import BaseModel, Field

from yuanboot.configuration import Configuration
from yuanboot.hosting import HostedService

request_id_context: ContextVar[str] = ContextVar("yuanboot_request_id", default="")
_PRIVATE = re.compile(r"password|secret|authorization|access.?token|credential", re.IGNORECASE)
_STANDARD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "request_id", "app"}


def _redact(value):
    if isinstance(value, dict):
        return {
            key: "***" if _PRIVATE.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


class LoggingOptions(BaseModel):
    level: str = "INFO"
    json_format: bool = Field(default=False, alias="json")
    console: bool = True
    file: str | None = None
    max_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    backup_count: int = Field(default=5, ge=0)
    loggers: dict[str, str] = Field(default_factory=dict)


class RequestContextFilter(logging.Filter):
    def __init__(self, application_name: str):
        super().__init__()
        self.application_name = application_name

    def filter(self, record):
        record.request_id = getattr(record, "request_id", "") or request_id_context.get()
        record.app = self.application_name
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record):
        data = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "app": getattr(record, "app", ""),
            "request_id": getattr(record, "request_id", ""),
            "message": record.getMessage(),
        }
        extra = {key: value for key, value in record.__dict__.items() if key not in _STANDARD}
        if extra:
            data["extra"] = _redact(extra)
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


class LoggingManager:
    def __init__(self, configuration: Configuration):
        self.options = LoggingOptions.model_validate(configuration.get("yuanboot.logging", {}))
        name = configuration.get_string("app") or configuration.get_string(
            "yuanboot.application.name", "yuanboot"
        )
        self.logger = logging.getLogger("yuanboot")
        self._old_level, self._old_propagate = self.logger.level, self.logger.propagate
        self._logger_levels = {}
        self._handlers: list[logging.Handler] = []
        self._closed = False
        level = self.options.level.upper()
        if level not in logging.getLevelNamesMapping():
            raise ValueError("Invalid logging level")
        formatter = (
            JsonFormatter()
            if self.options.json_format
            else logging.Formatter(
                "%(asctime)s %(levelname)s [%(app)s] %(name)s request_id=%(request_id)s %(message)s"
            )
        )
        try:
            if self.options.console:
                self._handlers.append(logging.StreamHandler())
            if self.options.file:
                path = Path(self.options.file).expanduser()
                path.parent.mkdir(parents=True, exist_ok=True)
                self._handlers.append(
                    RotatingFileHandler(
                        path,
                        maxBytes=self.options.max_bytes,
                        backupCount=self.options.backup_count,
                        encoding="utf-8",
                    )
                )
            for handler in self._handlers:
                handler.setFormatter(formatter)
                handler.addFilter(RequestContextFilter(name))
                self.logger.addHandler(handler)
            self.logger.setLevel(level)
            self.logger.propagate = False
            levels = {"httpx": "WARNING", **self.options.loggers}
            for logger_name, logger_level in levels.items():
                target = logging.getLogger(logger_name)
                self._logger_levels[target] = target.level
                target.setLevel(logger_level.upper())
        except BaseException:
            self.close()
            raise

    def get_logger(self, name: str = "app") -> logging.Logger:
        return get_logger(name)

    def close(self):
        if self._closed:
            return
        self._closed = True
        for handler in self._handlers:
            self.logger.removeHandler(handler)
            handler.flush()
            handler.close()
        self._handlers.clear()
        self.logger.setLevel(self._old_level)
        self.logger.propagate = self._old_propagate
        for target, level in self._logger_levels.items():
            target.setLevel(level)
        self._logger_levels.clear()


def get_logger(name: str = "app") -> logging.Logger:
    return logging.getLogger(name if name.startswith("yuanboot.") else "yuanboot." + name)


class LoggingLifecycle(HostedService):
    def __init__(self, manager: LoggingManager):
        self.manager = manager


def add_logging(services):
    def logger(manager: LoggingManager) -> logging.Logger:
        return manager.get_logger()

    services.add_singleton(LoggingManager)
    services.add_transient(logging.Logger, logger)
    services.add_hosted_service(LoggingLifecycle)
    return services
