"""Application logging with request correlation, JSON and rotating files."""

from __future__ import annotations

import json
import logging
import re
import sys
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from yuanboot.configuration import Configuration
from yuanboot.hosting import HostedService
from yuanboot.terminal import ColorMode, colorize, print_banner, use_color

request_id_context: ContextVar[str] = ContextVar("yuanboot_request_id", default="")
_PRIVATE = re.compile(r"password|secret|authorization|access.?token|credential", re.IGNORECASE)
_STANDARD = set(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "request_id",
    "app",
    "color_message",
    "_yuanboot_color",
    "_yuanboot_value_color",
}


def server_log_config() -> dict:
    return json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))


class TextFormatter(logging.Formatter):
    """Yuanboot zap/logrus console layout, with hundredths of a second."""

    def __init__(self, log_type="zap", color: ColorMode = "auto"):
        super().__init__()
        self.log_type = log_type
        self.color = color

    def format(self, record):
        timestamp = time.strftime("%Y/%m/%d %H:%M:%S", self.converter(record.created))
        timestamp += f".{int(record.msecs) // 10:02d}"
        prefix = f"yuanboot-nio-{record.process}-{record.thread}"
        level = {"WARNING": "WARN", "CRITICAL": "FATAL"}.get(record.levelname, record.levelname)
        message = record.getMessage()
        if use_color(self.color):
            if whole_color := getattr(record, "_yuanboot_color", None):
                message = colorize(message, whole_color, True)
            elif value_color := getattr(record, "_yuanboot_value_color", None):
                # Keep the original record clean for file/JSON handlers.
                if isinstance(record.args, tuple):
                    message = str(record.msg) % tuple(
                        colorize(value, value_color, True) for value in record.args
                    )
        if self.log_type == "logrus":
            text = f"{timestamp} - [{prefix}] - [{level}] {message} level={level}"
        else:
            caller = f"{Path(record.pathname).parent.name}/{record.filename}:{record.lineno}"
            text = f"[{prefix}] {timestamp}\t{level}\t{caller}\t{message}"
        extra = {key: value for key, value in record.__dict__.items() if key not in _STANDARD}
        if request_id := getattr(record, "request_id", "") or request_id_context.get():
            extra["request_id"] = request_id
        if extra:
            text += " " + " ".join(
                f"{key}={value}" for key, value in sorted(_redact(extra).items())
            )
        if record.exc_info:
            text += "\n" + self.formatException(record.exc_info)
        if record.stack_info:
            text += "\n" + self.formatStack(record.stack_info)
        return text


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
    color: ColorMode = "auto"
    banner: bool = True
    file: str | None = None
    max_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    backup_count: int = Field(default=5, ge=0)
    loggers: dict[str, str] = Field(default_factory=dict)
    log_type: Literal["zap", "logrus"] = "zap"


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
        self.logger = logging.getLogger()
        self._old_level, self._old_propagate = self.logger.level, self.logger.propagate
        self._logger_levels = {}
        self._logger_states = {}
        self._handlers: list[logging.Handler] = []
        self._closed = False
        level = self.options.level.upper()
        if level not in logging.getLevelNamesMapping():
            raise ValueError("Invalid logging level")
        try:
            # Route framework, application and server logs through one handler set.
            for logger_name in ("", "yuanboot", "uvicorn", "uvicorn.error", "uvicorn.access"):
                target = logging.getLogger(logger_name)
                self._logger_states[target] = (
                    target.handlers[:],
                    target.level,
                    target.propagate,
                    target.disabled,
                )
                target.handlers = []
                target.setLevel(logging.NOTSET)
                target.propagate = True
                target.disabled = logger_name == "uvicorn.access"
            if self.options.console:
                self._handlers.append(logging.StreamHandler(sys.stdout))
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
                handler.setFormatter(
                    JsonFormatter()
                    if self.options.json_format
                    else TextFormatter(
                        self.options.log_type,
                        self.options.color
                        if not isinstance(handler, RotatingFileHandler)
                        else "never",
                    )
                )
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

    def print_banner(self):
        if self.options.banner and self.options.console and not self.options.json_format:
            for handler in self._handlers:
                if isinstance(handler, logging.StreamHandler) and not isinstance(
                    handler, logging.FileHandler
                ):
                    print_banner(mode=self.options.color, stream=handler.stream)

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
        for target, (handlers, level, propagate, disabled) in self._logger_states.items():
            target.handlers = handlers
            target.setLevel(level)
            target.propagate = propagate
            target.disabled = disabled
        self._logger_states.clear()


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
