import json

import pytest
from pydantic import BaseModel

from yuanboot import Configuration, ConfigurationBuilder
from yuanboot.web.application import server_address


def test_layered_configuration(tmp_path, monkeypatch):
    (tmp_path / "config.yml").write_text(
        'database:\n  host: localhost\n  port: 5432\n  password: "${DB_SECRET:default}"\n'
        'url: "https://${DOMAIN:example.com}/path"\n'
    )
    (tmp_path / "config_prod.yml").write_text("database:\n  port: 5433\n")
    monkeypatch.setenv("YUANBOOT_PROFILE", "prod")
    monkeypatch.setenv("YUANBOOT_DATABASE__HOST", "remote")
    monkeypatch.setenv("YUANBOOT_PORT", "7000")
    monkeypatch.setenv("DB_SECRET", "s3cret")
    config = (
        ConfigurationBuilder(tmp_path)
        .add_defaults({"enabled": True})
        .add_yaml_file()
        .add_environment()
        .add_flag_args(["--port", "9000", "--unrelated", "value"])
        .build()
    )
    assert config.profile == "prod"
    assert config.get_bool("enabled") is True
    assert config.get_int("database.port") == 5433
    assert config.get_string("DATABASE.HOST") == "remote"
    assert config.get_string("database.password") == "s3cret"
    assert config.get_string("url") == "https://example.com/path"
    assert server_address(config) == ("0.0.0.0", 9000)
    values = config.to_dict()
    values["database"]["host"] = "changed"
    assert config.get_string("database.host") == "remote"


def test_json_and_model_binding(tmp_path):
    class Settings(BaseModel):
        enabled: bool
        retries: int

    (tmp_path / "settings.json").write_text(
        json.dumps({"feature": {"enabled": True, "retries": 3}})
    )
    config = ConfigurationBuilder(tmp_path).add_json_file("settings").build()
    assert config.bind(Settings, "feature").retries == 3
    assert config.get_section("feature").get_bool("enabled")


def test_missing_invalid_and_profile_only_files(tmp_path):
    with pytest.raises(FileNotFoundError):
        ConfigurationBuilder(tmp_path).add_yaml_file().build()
    (tmp_path / "config_dev.yml").write_text("hello: world\n")
    assert ConfigurationBuilder(tmp_path).add_yaml_file().build().get("hello") == "world"
    (tmp_path / "config.yml").write_text("- not-a-mapping\n")
    with pytest.raises(ValueError, match="mapping"):
        ConfigurationBuilder(tmp_path).add_yaml_file().build()
    with pytest.raises(ValueError, match="Profile"):
        ConfigurationBuilder().build(profile="../outside")


def test_missing_interpolation_and_strict_boolean(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_YUANBOOT_SECRET", raising=False)
    (tmp_path / "config.yml").write_text('secret: "${MISSING_YUANBOOT_SECRET}"\n')
    with pytest.raises(ValueError, match="Missing configuration"):
        ConfigurationBuilder(tmp_path).add_yaml_file().build()
    assert not Configuration({"enabled": "false"}).get_bool("enabled")
    with pytest.raises(ValueError, match="boolean"):
        Configuration({"enabled": "maybe"}).get_bool("enabled")


def test_host_port_and_address_override():
    config = Configuration(
        {"yuanboot": {"application": {"server": {"host": "127.0.0.1", "port": 8765}}}}
    )
    assert server_address(config) == ("127.0.0.1", 8765)
    config = Configuration({"yuanboot": {"application": {"server": {"address": "[::1]:8000"}}}})
    assert server_address(config) == ("::1", 8000)
    with pytest.raises(ValueError, match="port"):
        server_address(Configuration({"port": -1}))
