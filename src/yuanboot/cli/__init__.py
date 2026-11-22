import argparse
import os
import signal
import sys
import typing
from pathlib import Path

from yuanboot import __version__
from yuanboot import logging as framework_logging
from yuanboot.cli.environment import _dependencies_ready as _dependencies_ready
from yuanboot.cli.environment import _install_project, _prepare_environment
from yuanboot.cli.process import _external_environment, _external_runtime, _run_process
from yuanboot.cli.scaffolding import TEMPLATES, create_project
from yuanboot.compat import load_toml
from yuanboot.configuration import ConfigurationBuilder
from yuanboot.environment import PROFILES
from yuanboot.terminal import print_banner
from yuanboot.web.application import server_address


def _parser():
    parser = argparse.ArgumentParser(
        prog="yuanbootctl-python", description="yuanboot Python project tools"
    )
    parser.add_argument("--version", action="version", version=f"yuanbootctl-python {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.required = True
    new = commands.add_parser("new", help="Create an application from a template")
    new.add_argument("template", nargs="?")
    new.add_argument("-l", "--list", "--templates", action="store_true", dest="list_templates")
    new.add_argument("-n", "--name", "--projectName", default="demo")
    new.add_argument("-p", "--path", default=".")
    new.add_argument("--framework-version", help="PyPI framework version (default: tool version)")
    new.add_argument("--framework-repo", help="Use a Git repository instead of PyPI")
    new.add_argument("--framework-ref", help="Use a Git ref instead of PyPI")
    new.add_argument("--install", action="store_true", help="Create .venv and install dependencies")
    new.add_argument("--python", help="Python interpreter used to create .venv")
    new.add_argument("--index-url", help="Package index for dependency installation")
    install = commands.add_parser("install", help="Install backend dependencies in project .venv")
    install.add_argument("-p", "--path", default=".")
    install.add_argument("--python", help="Python interpreter used to create .venv")
    install.add_argument("--index-url", help="Package index for dependency installation")
    run = commands.add_parser("run", help="Run the current project's web or console host")
    run.add_argument("-p", "--path", default=".")
    run.add_argument("--profile", choices=PROFILES)
    run.add_argument("--host")
    run.add_argument("--port", type=int)
    run.add_argument("--reload", action="store_true")
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--python", help="Use a Python environment with your project's dependencies")
    run.add_argument(
        "--install", action="store_true", help="Install or refresh project dependencies"
    )
    run.add_argument("--index-url", help="Package index for dependency installation")
    build = commands.add_parser("build", help="Build wheel and sdist using python -m build")
    build.add_argument("-p", "--path", default=".")
    build.add_argument("--wheel", action="store_true")
    build.add_argument("--sdist", action="store_true")
    build.add_argument("--outdir")
    build.add_argument("--python", help="Python interpreter used to build the project")
    build.add_argument("--index-url", help="Package index for dependency installation")
    commands.add_parser("version", help="Print framework version")
    return parser


def _project_directory(path):
    """Resolve an application directory or the unique backend of an Admin project."""
    project = Path(path).expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"Project directory does not exist: {project}")
    if (project / "pyproject.toml").is_file():
        return project
    backends = [
        manifest.parent.resolve()
        for manifest in sorted(project.glob("*-server/pyproject.toml"))
        if (project / (manifest.parent.name[: -len("-server")] + "-web")).is_dir()
    ]
    if len(backends) == 1:
        return backends[0]
    if backends:
        names = ", ".join(backend.name for backend in backends)
        raise ValueError(
            f"Multiple Admin backends found in {project}: {names}. "
            "Use --path to select a backend directory."
        )
    raise ValueError(
        f"No pyproject.toml found in {project}. "
        "Run from the project directory or use --path <project-directory>. "
        "For Admin projects, select the directory containing the server and web folders "
        "or the server directory itself."
    )


def _run(args):
    project = _project_directory(args.path)
    if project != Path(args.path).expanduser().resolve():
        print(f"Using Admin backend: {project}", flush=True)
    with (project / "pyproject.toml").open("rb") as stream:
        metadata = load_toml(stream)
    settings = metadata.get("tool", {}).get("yuanboot", {})
    if not settings:
        raise ValueError("Missing [tool.yuanboot] configuration in pyproject.toml")
    python = args.python
    env = os.environ.copy()
    if args.profile:
        env["YUANBOOT_PROFILE"] = args.profile
    if args.port is not None:
        env["YUANBOOT_PORT"] = str(args.port)
    if settings.get("kind", "web") == "console":
        if args.reload or args.workers != 1 or args.host or args.port is not None:
            raise ValueError("Console projects do not support web server flags")
        module = settings.get("module")
        if not module:
            raise ValueError("Console projects require tool.yuanboot.module")
        command = [python or sys.executable, "-m", module]
    else:
        target = settings.get("app")
        if not target:
            raise ValueError("Web projects require tool.yuanboot.app")
        if args.reload and args.workers != 1:
            raise ValueError("--reload cannot be combined with multiple workers")
        if args.workers < 1:
            raise ValueError("--workers must be positive")
        config = (
            ConfigurationBuilder(project)
            .add_yaml_file(optional=True)
            .add_environment()
            .add_flag_args(["--profile", args.profile] if args.profile else [])
            .build()
        )
        host, port = server_address(config)
        port = args.port if args.port is not None else port
        if not 0 <= port <= 65535:
            raise ValueError("Port must be between 0 and 65535")
        command = [
            python or sys.executable,
            "-m",
            "uvicorn",
            target,
            "--host",
            args.host or host,
            "--port",
            str(port),
            "--workers",
            str(args.workers),
            "--log-config",
            str(Path(framework_logging.__file__).with_suffix(".json")),
        ]
        if args.reload:
            command.append("--reload")
        if settings.get("factory"):
            command.append("--factory")
        tls = config.get_section("yuanboot.application.server.tls")
        for key, flag in (("cert", "--ssl-certfile"), ("key", "--ssl-keyfile")):
            if tls.get_string(key):
                command.extend([flag, tls.get_string(key)])
    python = _prepare_environment(
        project,
        metadata,
        args.python,
        args.index_url,
        refresh=args.install,
        allow_embedded=True,
    )
    command[0] = python or sys.executable
    if getattr(sys, "frozen", False) and not python:
        return _run_embedded(command[2:], project, env)
    with _external_runtime():
        return _run_process(command, cwd=project, env=_external_environment(env))


def _run_embedded(arguments, project, env):
    import runpy

    previous_directory = Path.cwd()
    previous_path, previous_argv = sys.path[:], sys.argv[:]
    previous_environment = os.environ.copy()
    previous_signals = {}
    try:
        os.chdir(project)
        sys.path.insert(0, str(project))
        os.environ.update(env)
        # Uvicorn re-raises signals after shutdown; its outer CLI should exit successfully.
        for sig in (signal.SIGINT, signal.SIGTERM):
            previous_signals[sig] = signal.signal(sig, lambda signum, frame: None)
        if arguments[0] == "uvicorn":
            from uvicorn.main import main as uvicorn_main

            uvicorn_main(
                args=arguments[1:], prog_name="yuanbootctl-python run", standalone_mode=False
            )
        else:
            sys.argv = [arguments[0]]
            runpy.run_module(arguments[0], run_name="__main__", alter_sys=True)
        return 0
    finally:
        for sig, handler in previous_signals.items():
            signal.signal(sig, handler)
        os.chdir(previous_directory)
        sys.path[:] = previous_path
        sys.argv[:] = previous_argv
        os.environ.clear()
        os.environ.update(previous_environment)


def main(argv: "typing.Union[typing.List[str], None]" = None) -> "int":
    if os.name == "nt":
        # Pipes on Windows otherwise use the ANSI code page, which cannot encode
        # the framework logo or non-ASCII project paths.
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            if args.list_templates:
                for template in TEMPLATES.values():
                    print(f"{template.name:14} {template.description}")
            else:
                if not args.template:
                    parser.error("new requires TEMPLATE or --list")
                if not args.install and (args.python or args.index_url):
                    raise ValueError("new --python and --index-url require --install")
                destination = create_project(
                    args.template,
                    args.name,
                    args.path,
                    framework_repo=args.framework_repo,
                    framework_ref=args.framework_ref,
                    framework_version=args.framework_version,
                )
                print_banner(cli=True)
                print(f"Created {args.template}: {destination}")
                backend = (
                    destination / (args.name + "-server")
                    if args.template == "admin"
                    else destination
                )
                print(f'cd "{backend}"')
                if args.install:
                    _install_project(backend, args.python, args.index_url)
                elif not getattr(sys, "frozen", False):
                    print("yuanbootctl-python install")
                print("yuanbootctl-python run")
                if args.template == "admin":
                    frontend = destination / (args.name + "-web")
                    print(f'Frontend: cd "{frontend}" && pnpm install && pnpm dev')
        elif args.command == "run":
            return _run(args)
        elif args.command == "install":
            _install_project(_project_directory(args.path), args.python, args.index_url)
        elif args.command == "build":
            project = _project_directory(args.path)
            if project != Path(args.path).expanduser().resolve():
                print(f"Using Admin backend: {project}", flush=True)
            with (project / "pyproject.toml").open("rb") as stream:
                metadata = load_toml(stream)
            executable = _prepare_environment(
                project, metadata, args.python, args.index_url, build=True
            )
            command = [executable, "-m", "build"]
            for option in ("wheel", "sdist"):
                if getattr(args, option):
                    command.append("--" + option)
            if args.outdir:
                command.extend(["--outdir", args.outdir])
            environment = _external_environment(os.environ)
            if args.index_url:
                environment["PIP_INDEX_URL"] = args.index_url
            with _external_runtime():
                return _run_process(
                    command,
                    cwd=project,
                    env=environment,
                )
        else:
            print_banner(cli=True)
            print(f"yuanbootctl-python {__version__}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"yuanbootctl-python: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
