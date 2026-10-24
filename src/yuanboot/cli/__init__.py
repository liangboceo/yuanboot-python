from __future__ import annotations

import argparse
import importlib.util
import os
import signal
import subprocess
import sys
import tomllib
from contextlib import contextmanager
from pathlib import Path

from yuanboot import __version__
from yuanboot.cli.scaffolding import FRAMEWORK_REPOSITORY, TEMPLATES, create_project
from yuanboot.configuration import ConfigurationBuilder
from yuanboot.environment import PROFILES
from yuanboot.web.application import server_address


def _run_process(command, **options):
    """Forward container/process signals to the managed server before waiting for exit."""
    if os.name == "posix":
        # The CLI forwards terminal signals; isolating the child prevents duplicate SIGINTs.
        options.setdefault("start_new_session", True)
    with subprocess.Popen(command, **options) as process:
        previous = {}
        forwarded_signal = None

        def forward(signum, frame):
            nonlocal forwarded_signal
            forwarded_signal = signum
            if process.poll() is None:
                process.send_signal(signum)

        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                previous[sig] = signal.signal(sig, forward)
            code = process.wait()
            # Uvicorn re-raises a handled signal after its graceful shutdown.
            if forwarded_signal is not None and code == -forwarded_signal:
                return 0
            return code if code >= 0 else 128 - code
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def _parser():
    parser = argparse.ArgumentParser(
        prog="yuanbootctl-python", description="yuanboot Python project tools"
    )
    parser.add_argument("--version", action="version", version=f"yuanbootctl-python {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new", help="Create an application from a template")
    new.add_argument("template", nargs="?")
    new.add_argument("-l", "--list", "--templates", action="store_true", dest="list_templates")
    new.add_argument("-n", "--name", "--projectName", default="demo")
    new.add_argument("-p", "--path", default=".")
    new.add_argument("--framework-repo", default=FRAMEWORK_REPOSITORY)
    new.add_argument("--framework-ref", default="v" + __version__)
    run = commands.add_parser("run", help="Run the current project's web or console host")
    run.add_argument("-p", "--path", default=".")
    run.add_argument("--profile", choices=PROFILES)
    run.add_argument("--host")
    run.add_argument("--port", type=int)
    run.add_argument("--reload", action="store_true")
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--python", help="Use a Python environment with your project's dependencies")
    build = commands.add_parser("build", help="Build wheel and sdist using python -m build")
    build.add_argument("-p", "--path", default=".")
    build.add_argument("--wheel", action="store_true")
    build.add_argument("--sdist", action="store_true")
    build.add_argument("--outdir")
    build.add_argument("--python", help="Python interpreter with the build package installed")
    commands.add_parser("version", help="Print framework version")
    return parser


def _run(args):
    project = Path(args.path).expanduser().resolve()
    with (project / "pyproject.toml").open("rb") as stream:
        settings = tomllib.load(stream).get("tool", {}).get("yuanboot", {})
    if not settings:
        raise ValueError("Missing [tool.yuanboot] configuration in pyproject.toml")
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
        command = [args.python or sys.executable, "-m", module]
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
            args.python or sys.executable,
            "-m",
            "uvicorn",
            target,
            "--host",
            args.host or host,
            "--port",
            str(port),
            "--workers",
            str(args.workers),
        ]
        if args.reload:
            command.append("--reload")
        if settings.get("factory"):
            command.append("--factory")
        tls = config.get_section("yuanboot.application.server.tls")
        for key, flag in (("cert", "--ssl-certfile"), ("key", "--ssl-keyfile")):
            if tls.get_string(key):
                command.extend([flag, tls.get_string(key)])
    if getattr(sys, "frozen", False) and not args.python:
        return _run_embedded(command[2:], project, env)
    with _external_runtime():
        return _run_process(command, cwd=project, env=_external_environment(env))


def _external_environment(env):
    env = env.copy()
    if getattr(sys, "frozen", False):
        for key in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
            original = env.get(key + "_ORIG")
            if original is None:
                env.pop(key, None)
            else:
                env[key] = original
    return env


@contextmanager
def _external_runtime():
    """Keep bundled shared libraries out of an external Python interpreter's search path."""
    frozen_windows = getattr(sys, "frozen", False) and sys.platform == "win32"
    if frozen_windows:
        import ctypes

        ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        yield
    finally:
        if frozen_windows:
            ctypes.windll.kernel32.SetDllDirectoryW(sys._MEIPASS)


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


def main(argv: list[str] | None = None) -> int:
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
                destination = create_project(
                    args.template,
                    args.name,
                    args.path,
                    framework_repo=args.framework_repo,
                    framework_ref=args.framework_ref,
                )
                print(f"Created {args.template}: {destination}")
                print(f'cd "{destination}"')
                if not getattr(sys, "frozen", False):
                    print('python -m pip install -e ".[dev]"')
                print("yuanbootctl-python run")
        elif args.command == "run":
            return _run(args)
        elif args.command == "build":
            executable = args.python
            if getattr(sys, "frozen", False) and not executable:
                suffix = "Scripts/python.exe" if os.name == "nt" else "bin/python"
                candidate = Path(args.path).expanduser().resolve() / ".venv" / suffix
                if not candidate.is_file():
                    raise ValueError(
                        "build requires a Python environment: "
                        "install build, then use --python /path/to/python"
                    )
                executable = str(candidate)
            if not executable and importlib.util.find_spec("build") is None:
                raise ValueError('Install the build tool first: python -m pip install "build>=1.2"')
            command = [executable or sys.executable, "-m", "build"]
            for option in ("wheel", "sdist"):
                if getattr(args, option):
                    command.append("--" + option)
            if args.outdir:
                command.extend(["--outdir", args.outdir])
            with _external_runtime():
                return _run_process(
                    command,
                    cwd=Path(args.path).expanduser(),
                    env=_external_environment(os.environ),
                )
        else:
            print(f"yuanbootctl-python {__version__}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"yuanbootctl-python: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
