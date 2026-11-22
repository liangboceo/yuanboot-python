"""Project virtual environments, dependency checks and pip installation."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from yuanboot.compat import load_toml

from .process import _external_environment, _external_runtime, _run_process


def _venv_python(project):
    suffix = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return project / ".venv" / suffix


def _ensure_requirements(project):
    requirements = project / "requirements.txt"
    if not requirements.exists():
        requirements.write_text(
            "# Dependency versions are maintained in pyproject.toml.\n-e .[dev]\n",
            encoding="utf-8",
        )
    if project.name.endswith("-server"):
        frontend = project.parent / (project.name[: -len("-server")] + "-web")
        requirements = project.parent / "requirements.txt"
        if frontend.is_dir() and not requirements.exists():
            requirements.write_text(
                "# Install from the Admin project root.\n-e "
                + json.dumps("./" + project.name + "[dev]")
                + "\n",
                encoding="utf-8",
            )


def _requirements_files(project):
    paths = []
    if project.name.endswith("-server"):
        frontend = project.parent / (project.name[: -len("-server")] + "-web")
        parent_requirements = project.parent / "requirements.txt"
        if frontend.is_dir() and parent_requirements.is_file():
            paths.append(parent_requirements)
    if (project / "requirements.txt").is_file():
        paths.append(project / "requirements.txt")
    return paths


def _dependencies_ready(python, metadata, project, *, build=False):
    requirements = list(metadata.get("project", {}).get("dependencies", []))
    if build:
        requirements.extend(
            metadata.get("project", {}).get("optional-dependencies", {}).get("dev", [])
        )
        requirements.append("build")
    files = _requirements_files(project)
    if not requirements and not files:
        return True
    script = """
import json
import os
import sys
from pathlib import Path
try:
    from importlib.metadata import distribution
except ImportError:
    try:
        from importlib_metadata import distribution
    except ImportError:
        sys.exit(1)
try:
    from packaging.requirements import Requirement
except ImportError:
    sys.exit(1)
seen = set()
def check(value, extras=()):
    requirement = Requirement(value)
    if requirement.marker and not any(
        requirement.marker.evaluate({"extra": extra}) for extra in ("",) + tuple(extras)
    ):
        return
    installed = distribution(requirement.name)
    if requirement.specifier and not requirement.specifier.contains(installed.version):
        raise ValueError("Incompatible dependency")
    key = (requirement.name.lower().replace("_", "-"), tuple(sorted(requirement.extras)))
    if key in seen:
        return
    seen.add(key)
    for child in installed.requires or ():
        check(child, requirement.extras)
try:
    for requirement in json.loads(sys.argv[1]):
        check(requirement)
    if json.loads(sys.argv[4]):
        from pip._internal.network.session import PipSession
        from pip._internal.req.req_file import parse_requirements
        from pip._internal.req.constructors import install_req_from_parsed_requirement
        metadata = json.loads(sys.argv[2])
        project = Path(sys.argv[3]).resolve()
        with PipSession() as session:
            for filename in json.loads(sys.argv[4]):
                filename = Path(filename)
                os.chdir(str(filename.parent))
                for parsed in parse_requirements(str(filename), session=session):
                    requirement = install_req_from_parsed_requirement(parsed)
                    local_project = (
                        requirement.link is not None and requirement.link.is_file
                        and Path(requirement.link.file_path).resolve() == project
                    )
                    if local_project:
                        for extra in requirement.extras:
                            optional = metadata.get("project", {}).get("optional-dependencies", {})
                            for dependency in optional.get(extra, []):
                                check(dependency)
                    elif requirement.req is not None:
                        if parsed.constraint:
                            try:
                                distribution(requirement.req.name)
                            except Exception:
                                continue
                        check(str(requirement.req))
                    else:
                        raise ValueError("Source dependency needs installation")
except Exception:
    sys.exit(1)
"""
    with _external_runtime():
        return (
            subprocess.call(
                [
                    python,
                    "-c",
                    script,
                    json.dumps(requirements),
                    json.dumps(metadata),
                    str(project),
                    json.dumps([str(path) for path in files]),
                ],
                cwd=project,
                env=_external_environment(os.environ),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            == 0
        )


def _prepare_environment(
    project,
    metadata,
    python=None,
    index_url=None,
    *,
    refresh=False,
    build=False,
    allow_embedded=False,
):
    explicit = python is not None
    if python and not Path(python).is_absolute() and Path(python).parent != Path("."):
        python = str((project / python).resolve())
    if not python:
        local_python = _venv_python(project)
        if local_python.is_file():
            python = str(local_python)
        elif not getattr(sys, "frozen", False):
            python = sys.executable
        elif allow_embedded and not refresh:
            return None
    if refresh or not python or not _dependencies_ready(python, metadata, project, build=build):
        if explicit:
            _install_dependencies(project, python, index_url)
        else:
            python = str(_install_project(project, index_url=index_url))
        if build and not _dependencies_ready(python, metadata, project, build=True):
            _pip_install(project, python, ["build"], index_url)
    return python


def _install_project(project, python=None, index_url=None):
    executable = _venv_python(project)
    env = _external_environment(os.environ)
    with _external_runtime():
        if not executable.is_file():
            if (project / ".venv").exists():
                raise ValueError(
                    f"Incomplete virtual environment: {project / '.venv'}. "
                    "Restore or remove it before running install again."
                )
            interpreter = python
            if not interpreter:
                interpreter = (
                    shutil.which("python3") or shutil.which("python")
                    if getattr(sys, "frozen", False)
                    else sys.executable
                )
            if not interpreter:
                raise ValueError(
                    "Installing dependencies requires Python; use --python <executable>."
                )
            print(f"Creating virtual environment: {project / '.venv'}", flush=True)
            if _run_process(
                [interpreter, "-m", "venv", str(project / ".venv")], cwd=project, env=env
            ):
                raise ValueError(
                    "Could not create .venv. Check that Python's venv module is installed."
                )
    _install_dependencies(project, str(executable), index_url)
    print(f"Dependencies ready: {executable}", flush=True)
    return executable


def _pip_install(project, python, arguments, index_url=None):
    index = ["--index-url", index_url] if index_url else []
    with _external_runtime():
        code = _run_process(
            [python, "-m", "pip", "install", *index, *arguments],
            cwd=project,
            env=_external_environment(os.environ),
        )
    if code:
        raise ValueError(
            "Dependency installation failed. See the pip output above; "
            "retry with yuanbootctl-python install after resolving the error."
        )


def _install_dependencies(project, python, index_url=None):
    _ensure_requirements(project)
    print(f"Installing backend dependencies: {project}", flush=True)
    with _external_runtime():
        environment = _external_environment(os.environ)
        if subprocess.call(
            [python, "-c", "import pip"],
            cwd=project,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        ) and _run_process([python, "-m", "ensurepip", "--upgrade"], cwd=project, env=environment):
            raise ValueError("Could not initialize pip in the selected Python environment.")
    _pip_install(project, python, ["--upgrade", "pip"], index_url)
    _pip_install(project, python, ["-e", ".[dev]"], index_url)
    for requirements in _requirements_files(project):
        _pip_install(
            requirements.parent,
            python,
            ["-r", str(requirements), "-e", str(project) + "[dev]"],
            index_url,
        )
    with (project / "pyproject.toml").open("rb") as stream:
        metadata = load_toml(stream)
    if not _dependencies_ready(python, metadata, project, build=True):
        _pip_install(project, python, ["build"], index_url)
