"""Layered YAML/JSON, profile, environment and command-line configuration."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Generic, TypeVar

import yaml
from pydantic import BaseModel

from yuanboot.environment import validate_profile

T = TypeVar("T", bound=BaseModel)
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::([^}]*))?\}")


def _merge(target: dict, source: Mapping) -> None:
    for key, value in source.items():
        if not isinstance(key, str):
            raise ValueError("Configuration keys must be strings")
        key = key.lower()
        if isinstance(value, Mapping):
            if not isinstance(target.get(key), dict):
                target[key] = {}
            _merge(target[key], value)
        else:
            target[key] = copy.deepcopy(value)


def _set(target: dict, path: str, value: Any) -> None:
    parts = path.lower().split(".")
    if not all(parts):
        raise ValueError(f"Invalid configuration path: {path}")
    for key in parts[:-1]:
        if not isinstance(target.get(key), dict):
            target[key] = {}
        target = target[key]
    target[parts[-1]] = value


class Configuration:
    def __init__(self, values: Mapping | None = None, *, profile: str = "dev") -> None:
        self._values: dict = {}
        _merge(self._values, values or {})
        self.profile = validate_profile(profile)
        self._reload_lock = threading.RLock()
        self._reload_factory = None
        self._sources: list = []
        self._callbacks: list = []
        self.poll_interval: float | None = None
        self.version = 0
        self.last_refresh_error: str | None = None
        self._closed = False

    def get(self, path: str, default: Any = None) -> Any:
        value: Any = self._values
        for key in path.lower().split("."):
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        return copy.deepcopy(value)

    def get_string(self, path: str, default: str = "") -> str:
        value = self.get(path, default)
        return default if value is None else str(value)

    def get_int(self, path: str, default: int = 0) -> int:
        return int(self.get(path, default))

    def get_bool(self, path: str, default: bool = False) -> bool:
        value = self.get(path, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false", "1", "0", "yes", "no"}:
            return value.lower() in {"true", "1", "yes"}
        raise ValueError(f"Configuration {path!r} must be boolean")

    def get_section(self, path: str) -> Configuration:
        value = self.get(path, {})
        if not isinstance(value, dict):
            raise ValueError(f"Configuration section {path!r} must be a mapping")
        return Configuration(value, profile=self.profile)

    def bind(self, model: type[T], path: str = "") -> T:
        return model.model_validate(self.get(path) if path else self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._values)

    def on_change(self, callback):
        """Subscribe a synchronous callback. Async handlers use configuration_changed events."""
        self._callbacks.append(callback)
        return self

    def reload(self) -> bool:
        with self._reload_lock:
            if self._closed:
                raise RuntimeError("Configuration is closed")
            if self._reload_factory is None:
                return False
            # Fetch/parse all sources before swapping so errors retain the last good snapshot.
            values = self._reload_factory()
            self.last_refresh_error = None
            if values == self._values:
                return False
            self._values = values
            self.version += 1
        for callback in tuple(self._callbacks):
            callback(self)
        return True

    def close(self):
        if self._closed:
            return
        self._closed = True
        errors = []
        for source in reversed(self._sources):
            try:
                if callable(getattr(source, "close", None)):
                    source.close()
            except Exception as exc:
                errors.append(exc)
        self._sources.clear()
        if errors:
            raise ExceptionGroup("Configuration source cleanup failed", errors)

    def options(self, model: type[T], path: str = "") -> OptionsSnapshot[T]:
        return OptionsSnapshot(self, model, path)


class OptionsSnapshot(Generic[T]):
    """Rebind current configuration on access, like Go OptionsSnapshot.CurrentValue."""

    def __init__(self, configuration: Configuration, model: type[T], path: str = ""):
        self.configuration, self.model, self.path = configuration, model, path

    @property
    def current_value(self) -> T:
        return self.configuration.bind(self.model, self.path)


class ConfigurationBuilder:
    """Sources: defaults < base file < profile file < environment < CLI flags."""

    def __init__(self, directory: str | Path = ".") -> None:
        self.directory = Path(directory)
        self._defaults: dict = {}
        self._files: list[tuple[Path, bool]] = []
        self._env_prefix: str | None = None
        self._args: Sequence[str] | None = None
        self._flags = False
        self._sources: list = []
        self._nacos: list = []

    def add_defaults(self, values: Mapping) -> ConfigurationBuilder:
        _merge(self._defaults, values)
        return self

    def add_yaml_file(self, name: str = "config", *, optional: bool = False):
        self._files.append((Path(name if Path(name).suffix else name + ".yml"), optional))
        return self

    def add_json_file(self, name: str = "config", *, optional: bool = False):
        self._files.append((Path(name if Path(name).suffix else name + ".json"), optional))
        return self

    def add_environment(self, prefix: str = "YUANBOOT_") -> ConfigurationBuilder:
        self._env_prefix = prefix
        return self

    def add_flag_args(self, args: Sequence[str] | None = None) -> ConfigurationBuilder:
        self._flags, self._args = True, args
        return self

    def add_source(self, source) -> ConfigurationBuilder:
        """Add a provider implementing load()->Mapping and optionally close()/poll_interval."""
        self._sources.append(source)
        return self

    def add_nacos(self, options=None, *, data_id: str | None = None, optional: bool = False):
        """Options may be omitted to bootstrap from yuanboot.cloud.nacos in local config/env."""
        self._nacos.append((options, data_id, optional))
        return self

    def add_apollo(self, options):
        from yuanboot.components.apollo import ApolloConfigurationSource

        return self.add_source(ApolloConfigurationSource(options))

    def build(self, profile: str | None = None) -> Configuration:
        flags: dict = {}
        if self._flags:
            parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
            for flag in ("profile", "port", "app", "conf"):
                parser.add_argument(f"--{flag}")
            parser.add_argument("-f", "--config", dest="config")
            flags = vars(parser.parse_known_args(self._args)[0])
        prefix = self._env_prefix
        profile = (
            flags.get("profile")
            or (os.environ.get(prefix + "PROFILE") if prefix else None)
            or profile
            or "dev"
        )
        validate_profile(profile)
        directory = Path(flags.get("conf") or self.directory)
        values = copy.deepcopy(self._defaults)
        files = [(Path(flags["config"]), False)] if flags.get("config") else self._files
        for name, optional in files:
            base = directory / name
            overlay = base.with_name(f"{base.stem}_{profile}{base.suffix}")
            existing = [p for p in (base, overlay) if p.is_file()]
            if not existing and not optional:
                raise FileNotFoundError(base)
            for path in existing:
                with path.open(encoding="utf-8") as stream:
                    data = json.load(stream) if path.suffix == ".json" else yaml.safe_load(stream)
                if data is not None and not isinstance(data, dict):
                    raise ValueError(f"Configuration {path} must contain a mapping")
                _merge(values, data or {})

        def interpolate(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: interpolate(item) for key, item in value.items()}
            if isinstance(value, list):
                return [interpolate(item) for item in value]
            if not isinstance(value, str):
                return value

            def replace(match: re.Match) -> str:
                key, default = match.groups()
                if key not in os.environ and default is None:
                    raise ValueError(f"Missing configuration environment variable: {key}")
                return os.environ.get(key, default or "")

            return _PLACEHOLDER.sub(replace, value)

        def finish(base):
            final = copy.deepcopy(base)
            if prefix:
                for key, raw in sorted(os.environ.items()):
                    if key.startswith(prefix) and key != prefix + "PROFILE":
                        path = key[len(prefix) :].lower().replace("__", ".")
                        _set(final, path, yaml.safe_load(raw))
                for short in ("port", "app"):
                    if prefix + short.upper() in os.environ:
                        _set(final, short, os.environ[prefix + short.upper()])
            for key in ("port", "app"):
                if flags.get(key) is not None:
                    _set(final, key, flags[key])
            return Configuration(interpolate(final), profile=profile)

        sources = list(self._sources)
        for options, data_id, optional in self._nacos:
            from yuanboot.components.nacos import NacosConfigurationSource, NacosOptions

            options = options or NacosOptions.from_configuration(finish(values))
            if data_id is not None:
                options = options.model_copy(update={"data_id": data_id})
            sources.append(NacosConfigurationSource(options, optional=optional))

        def reload_values():
            merged = copy.deepcopy(values)
            for source in sources:
                _merge(merged, source.load())
            return finish(merged).to_dict()

        try:
            configuration = Configuration(reload_values(), profile=profile)
        except BaseException:
            for source in sources:
                if callable(getattr(source, "close", None)):
                    source.close()
            raise
        if sources:
            configuration._reload_factory = reload_values
            configuration._sources = sources
            intervals = [
                float(s.poll_interval)
                for s in sources
                if getattr(s, "poll_interval", None) is not None
            ]
            if intervals and min(intervals) <= 0:
                configuration.close()
                raise ValueError("Configuration polling interval must be positive")
            configuration.poll_interval = min(intervals) if intervals else None
        return configuration
