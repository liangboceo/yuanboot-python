"""Console branding and terminal colors."""

from __future__ import annotations

import os
import sys
from typing import Literal

from yuanboot._version import __version__

ColorMode = Literal["auto", "always", "never"]
COLORS = {"blue": 34, "green": 32, "yellow": 33, "red": 31}
LOGO = (
    "                                            █████                        █████   \n"
    "                                           ░░███                        ░░███    \n"
    " █████ ████ █████ ████  ██████   ████████   ░███████   ██████   ██████  ███████  \n"
    "░░███ ░███ ░░███ ░███  ░░░░░███ ░░███░░███  ░███░░███ ███░░███ ███░░███░░░███░   \n"
    " ░███ ░███  ░███ ░███   ███████  ░███ ░███  ░███ ░███░███ ░███░███ ░███  ░███    \n"
    " ░███ ░███  ░███ ░███  ███░░███  ░███ ░███  ░███ ░███░███ ░███░███ ░███  ░███ ███\n"
    " ░░███████  ░░████████░░████████ ████ █████ ████████ ░░██████ ░░██████   ░░█████ \n"
    "  ░░░░░███   ░░░░░░░░  ░░░░░░░░ ░░░░ ░░░░░ ░░░░░░░░   ░░░░░░   ░░░░░░     ░░░░░  \n"
    "  ███ ░███                                                                       \n"
    " ░░██████                                                                        \n"
    "  ░░░░░░                                                                         \n"
)


def use_color(mode: ColorMode = "auto", stream=None) -> bool:
    if mode != "auto":
        return mode == "always"
    if "NO_COLOR" in os.environ:
        return False
    if "FORCE_COLOR" in os.environ:
        return os.environ["FORCE_COLOR"] != "0"
    stream = sys.stdout if stream is None else stream
    return bool(getattr(stream, "isatty", lambda: False)() or os.getenv("PYCHARM_HOSTED"))


def colorize(value, color: str, enabled: bool) -> str:
    text = str(value)
    return f"\x1b[{COLORS[color]}m{text}\x1b[0m" if enabled else text


def banner(*, cli: bool = False, colors: bool = False) -> str:
    name = "yuanbootctl-python" if cli else "yuanboot"
    description = (
        "Project scaffolding and application tools for yuanboot-python."
        if cli
        else (
            "light and fast , dependency injection based micro-service framework written in Python."
        )
    )
    return (
        colorize(LOGO, "blue", colors)
        + "\n \n"
        + colorize(f":: {name} ::", "green", colors)
        + "   (version:  "
        + colorize(__version__, "blue", colors)
        + ")\n"
        + colorize(description, "blue", colors)
        + "\n \n"
    )


def print_banner(*, cli: bool = False, mode: ColorMode = "auto", stream=None) -> None:
    stream = sys.stdout if stream is None else stream
    stream.write(banner(cli=cli, colors=use_color(mode, stream)))
    stream.flush()
