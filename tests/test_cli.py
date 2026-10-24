import http.client
import os
import signal
import socket
import subprocess
import sys
import time
import tomllib

import pytest

from yuanboot.cli import main
from yuanboot.cli.scaffolding import TEMPLATES, create_project


def test_generated_dependency_pins_framework_git_tag(tmp_path):
    project = create_project(
        "webapi",
        "tagged",
        tmp_path,
        framework_repo="git@github.com:liangboceo/yuanboot-python.git",
        framework_ref="v0.1.0",
    )
    metadata = tomllib.loads((project / "pyproject.toml").read_text())
    assert metadata["project"]["dependencies"] == [
        "yuanboot @ git+ssh://git@github.com/liangboceo/yuanboot-python.git@v0.1.0"
    ]
    assert (
        "yuanboot[all] @ git+ssh://"
        in metadata["project"]["optional-dependencies"]["components"][0]
    )
    with pytest.raises(ValueError):
        create_project("webapi", "badref", tmp_path, framework_ref='v1"\ninvalid')
    assert not (tmp_path / "badref").exists()


def test_list_and_errors(tmp_path, capsys):
    assert main(["new", "--list"]) == 0
    assert "microservice" in capsys.readouterr().out
    assert main(["new", "unknown", "-p", str(tmp_path)]) == 1
    assert main(["new", "webapi", "-n", "../escape", "-p", str(tmp_path)]) == 1
    assert main(["version"]) == 0
    assert not list(tmp_path.iterdir())


def test_existing_directory_is_never_overwritten(tmp_path):
    destination = tmp_path / "demo"
    destination.mkdir()
    sentinel = destination / "important.txt"
    sentinel.write_text("keep")
    with pytest.raises(FileExistsError):
        create_project("webapi", "demo", tmp_path)
    assert sentinel.read_text() == "keep"


@pytest.mark.parametrize("template", TEMPLATES)
def test_generated_project_runs_its_tests_and_routes(template, tmp_path):
    name = "sample-" + template
    project = create_project(template, name, tmp_path)
    package = name.replace("-", "_")
    with (project / "pyproject.toml").open("rb") as stream:
        metadata = tomllib.load(stream)
    assert metadata["tool"]["yuanboot"]["module"] == f"{package}.main"
    assert metadata["tool"]["hatch"]["metadata"]["allow-direct-references"] is True
    assert (project / ".gitignore").exists()
    assert (project / "Dockerfile").exists()
    for profile in ("dev", "fat", "uat", "pro"):
        assert (project / f"config_{profile}.yml").exists()
    assert not (project / "config_prod.yml").exists()
    assert not (project / "config_cloud.yml").exists()
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    if template not in {"console", "grpc"}:
        script = f"""
from fastapi.testclient import TestClient
from {package}.main import create_app
with TestClient(create_app()) as client:
    assert client.get('/actuator/prometheus').status_code == 200
    if {template!r} in ('mvc', 'simpleweb'):
        assert client.get('/').status_code == 200
    if {template!r} in ('mvc', 'webapi', 'microservice'):
        response = client.post('/api/greet', json={{'name': 'tester'}})
        assert response.status_code == 200, response.text
        assert 'tester' in response.text
        assert client.post('/api/greet', json={{'name': ''}}).status_code == 422
"""
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=project, capture_output=True, text=True, timeout=30
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_run_dispatch_and_options(tmp_path, monkeypatch):
    from yuanboot import cli

    project = create_project("webapi", "demo", tmp_path)
    (project / "config_pro.yml").write_text(
        'yuanboot:\n  application:\n    server:\n      address: ":9100"\n'
    )
    calls = []
    monkeypatch.setattr(
        cli, "_run_process", lambda command, **kwargs: calls.append((command, kwargs)) or 0
    )
    assert main(["run", "-p", str(project), "--port", "9001", "--profile", "pro"]) == 0
    command, kwargs = calls[0]
    assert command[:3] == [sys.executable, "-m", "uvicorn"]
    assert command[command.index("--port") + 1] == "9001"
    assert kwargs["env"]["YUANBOOT_PROFILE"] == "pro"
    monkeypatch.setenv("YUANBOOT_PROFILE", "dev")
    assert main(["run", "-p", str(project), "--profile", "pro"]) == 0
    assert calls[-1][0][calls[-1][0].index("--port") + 1] == "9100"
    assert os.getcwd() != str(project)
    assert main(["run", "-p", str(project), "--reload", "--workers", "2"]) == 1
    assert main(["run", "-p", str(project), "--port", "-1"]) == 1
    console = create_project("console", "worker", tmp_path)
    assert main(["run", "-p", str(console)]) == 0
    assert calls[-1][0] == [sys.executable, "-m", "worker.main"]
    assert main(["run", "-p", str(console), "--reload"]) == 1


@pytest.mark.parametrize("template", ["webapi", "console"])
@pytest.mark.parametrize("stop_signal", [signal.SIGTERM, signal.SIGINT])
def test_real_cli_process_starts_and_stops_gracefully(template, stop_signal, tmp_path):
    project = create_project(template, "live_" + template, tmp_path)
    command = [sys.executable, "-m", "yuanboot", "run", "-p", str(project)]
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    if template != "console":
        command.extend(["--host", "127.0.0.1", "--port", str(port)])
    log = tmp_path / "server.log"
    with log.open("w") as output:
        process = subprocess.Popen(command, stdout=output, stderr=output, start_new_session=True)
        try:
            ready = False
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline and process.poll() is None:
                if template == "console":
                    ready = "is running" in log.read_text()
                else:
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=0.2)
                    try:
                        connection.request("GET", "/actuator/health/readiness")
                        response = connection.getresponse()
                        ready = response.status == 200
                        response.read()
                    except OSError:
                        pass
                    finally:
                        connection.close()
                if ready:
                    break
                time.sleep(0.05)
            assert ready, log.read_text()
            # Terminal signals target a process group, not just the CLI process.
            os.killpg(process.pid, stop_signal)
            assert process.wait(timeout=10) == 0, log.read_text()
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    assert (
        "stopped" if template == "console" else "Application shutdown complete"
    ) in log.read_text()
