from __future__ import annotations

import json
import keyword
import re
import shutil
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from yuanboot import __version__


@dataclass(frozen=True)
class ProjectTemplate:
    name: str
    description: str
    layers: tuple[str, ...]


TEMPLATES = {
    item.name: item
    for item in (
        ProjectTemplate(
            "webapi", "FastAPI endpoints, DI, validation and actuator", ("web", "webapi")
        ),
        ProjectTemplate("simpleweb", "Minimal HTTP application", ("web", "simpleweb")),
        ProjectTemplate("mvc", "Controllers, services and Jinja2 views", ("web", "mvc")),
        ProjectTemplate(
            "microservice",
            "Web API with a managed background worker",
            ("web", "webapi", "microservice"),
        ),
        ProjectTemplate("console", "Console host with managed background services", ("console",)),
        ProjectTemplate("grpc", "gRPC service with protobuf and managed host lifecycle", ("grpc",)),
    )
}

FRAMEWORK_REPOSITORY = "https://github.com/liangboceo/yuanboot-python.git"


def framework_requirement(*, repository=FRAMEWORK_REPOSITORY, ref=None, extras=""):
    if repository.startswith("git@"):
        repository = "ssh://" + repository.replace(":", "/", 1)
    repository = repository.removeprefix("git+")
    if not re.fullmatch(r"(?:ssh|https)://[A-Za-z0-9@._:/-]+", repository):
        raise ValueError("Framework repository must be a Git SSH/HTTPS URL")
    ref = ref or "v" + __version__
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", ref) or ".." in ref:
        raise ValueError("Invalid framework Git ref")
    name = f"yuanboot[{extras}]" if extras else "yuanboot"
    return f"{name} @ git+{repository}@{ref}"


def _walk(resource, prefix=Path()):
    for child in sorted(resource.iterdir(), key=lambda p: p.name):
        path = prefix / child.name
        if child.is_dir():
            yield from _walk(child, path)
        elif child.name.endswith(".tpl"):
            yield path.with_suffix(""), child.read_text(encoding="utf-8")


def create_project(
    template: str,
    name: str = "demo",
    path: str | Path = ".",
    *,
    framework_repo: str = FRAMEWORK_REPOSITORY,
    framework_ref: str | None = None,
) -> Path:
    if template not in TEMPLATES:
        raise ValueError(f"Unknown template {template!r}. Use 'yuanbootctl-python new --list'.")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
        raise ValueError(
            "Project name must start with a letter and contain letters, digits, '-' or '_'"
        )
    package = name.lower().replace("-", "_")
    if keyword.iskeyword(package) or package == "yuanboot":
        raise ValueError(f"Project name {name!r} conflicts with a Python keyword or the framework")
    rendered = {}
    root = files("yuanboot.cli").joinpath("templates")
    substitutions = {
        "__PROJECT__": name,
        "__PACKAGE__": package,
        "__TEMPLATE__": template,
        "__YUANBOOT_VERSION__": __version__,
        "__FRAMEWORK_REF__": framework_ref or "v" + __version__,
        "__KIND__": "console" if template in {"console", "grpc"} else "web",
        "__YUANBOOT_REQUIREMENT__": json.dumps(
            framework_requirement(
                repository=framework_repo,
                ref=framework_ref,
                extras="grpc" if template == "grpc" else "",
            )
        ),
        "__YUANBOOT_COMPONENTS_REQUIREMENT__": json.dumps(
            framework_requirement(repository=framework_repo, ref=framework_ref, extras="all")
        ),
    }
    for layer in ("common", *TEMPLATES[template].layers):
        for relative, content in _walk(root.joinpath(layer)):
            target = str(relative).replace("__PACKAGE__", package)
            for token, value in substitutions.items():
                content = content.replace(token, value)
            rendered[target] = content
    destination = Path(path).expanduser().resolve() / name
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also rejects existing empty directories and symlinks.
    destination.mkdir(exist_ok=False)
    try:
        for relative, content in rendered.items():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    except BaseException:
        shutil.rmtree(destination)
        raise
    return destination
