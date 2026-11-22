"""Project virtual environments, dependency checks and pip installation."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from yuanboot.compat import load_toml

from .process import _external_environment, _external_runtime, _run_process


def _venv_python(project):
    suffix = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return project / ".venv" / suffix


_BEGIN_RUNTIME = "# BEGIN yuanboot runtime dependencies (managed from pyproject.toml)"
_END_RUNTIME = "# END yuanboot runtime dependencies"


def _runtime_block(metadata):
    dependencies = metadata.get("project", {}).get("dependencies", [])
    return "\n".join([_BEGIN_RUNTIME, *dependencies, _END_RUNTIME]) + "\n"


def _ensure_requirements(project, metadata):
    """Sync generated runtime entries, preserving custom requirements and options."""
    requirements = project / "requirements.txt"
    if not requirements.exists():
        requirements.write_text(_runtime_block(metadata), encoding="utf-8")
    if project.name.endswith("-server"):
        frontend = project.parent / (project.name[: -len("-server")] + "-web")
        parent = project.parent / "requirements.txt"
        if frontend.is_dir() and not parent.exists():
            parent.write_text('-r "./' + project.name + '/requirements.txt"\n', encoding="utf-8")
    visited = set()

    def update(filename):
        filename = filename.resolve()
        if filename in visited or not filename.is_file():
            return
        visited.add(filename)
        original = filename.read_text(encoding="utf-8")
        content = re.sub(
            re.escape(_BEGIN_RUNTIME) + r".*?" + re.escape(_END_RUNTIME) + r"\n?",
            lambda match: _runtime_block(metadata),
            original,
            flags=re.S,
        )
        lines = []
        for line in content.splitlines(keepends=True):
            value = line.strip()
            include = re.match(
                r"^(?:-r\s*|--requirement(?:=|\s+)|-c\s*|--constraint(?:=|\s+))(.+)$", value
            )
            if include:
                target = include.group(1).split(" #", 1)[0].strip().strip("\"'")
                if not re.match(r"https?://", target):
                    update(filename.parent / target)
            value = re.sub(r"^(?:-e\s*|--editable(?:=|\s+))", "", value)
            value = value.split(" #", 1)[0].strip().strip("\"'")
            match = re.fullmatch(r"(.+?)(?:\[([^]]*)\])?", value)
            if match and (filename.parent / match.group(1)).resolve() == project:
                # Old templates installed the business package with [dev]. Only its
                # declared runtime dependencies belong in install/run.
                lines.append(_runtime_block(metadata))
                optional = metadata.get("project", {}).get("optional-dependencies", {})
                for extra in (match.group(2) or "").split(","):
                    if extra.strip() not in ("dev", "build"):
                        lines.extend(dep + "\n" for dep in optional.get(extra.strip(), []))
            else:
                lines.append(line)
        content = "".join(lines)
        if content != original:
            filename.write_text(content, encoding="utf-8")

    for filename in _requirements_files(project):
        update(filename)


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
                        for extra in requirement.extras - {"dev", "build"}:
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
    _ensure_requirements(project, metadata)
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
            _install_dependencies(project, python, index_url, build=build)
        else:
            python = str(_install_project(project, index_url=index_url, build=build))
    return python


def _install_project(project, python=None, index_url=None, *, build=False):
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
    _install_dependencies(project, str(executable), index_url, build=build)
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


def _install_dependencies(project, python, index_url=None, *, build=False):
    with (project / "pyproject.toml").open("rb") as stream:
        metadata = load_toml(stream)
    _ensure_requirements(project, metadata)
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
    dependencies = list(metadata.get("project", {}).get("dependencies", []))
    if build:
        dependencies.extend(
            metadata.get("project", {}).get("optional-dependencies", {}).get("dev", [])
        )
        dependencies.extend(
            [
                "build>=0.7,<0.8; python_version < '3.8'",
                "build>=1.2; python_version >= '3.8'",
            ]
        )
    files = _requirements_files(project)
    if not files and dependencies:
        _pip_install(project, python, dependencies, index_url)
    for requirements in files:
        _pip_install(
            requirements.parent, python, [*dependencies, "-r", str(requirements)], index_url
        )
