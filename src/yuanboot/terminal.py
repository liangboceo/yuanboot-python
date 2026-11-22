"""Console branding and terminal colors."""

import os
import sys

from typing_extensions import Literal

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


def _windows_ansi(stream):
    """Enable ANSI processing on the actual console handle, if supported."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    try:
        handle = msvcrt.get_osfhandle(stream.fileno())
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetConsoleMode.restype = wintypes.BOOL
        kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.SetConsoleMode.restype = wintypes.BOOL
        flags = wintypes.DWORD()
        if not kernel.GetConsoleMode(handle, ctypes.byref(flags)):
            return False
        return bool(kernel.SetConsoleMode(handle, flags.value | 0x0004))
    except (OSError, ValueError, AttributeError):
        return False


def use_color(mode: "ColorMode" = "auto", stream=None) -> "bool":
    if mode != "auto":
        return mode == "always"
    if "NO_COLOR" in os.environ:
        return False
    if "FORCE_COLOR" in os.environ:
        return os.environ["FORCE_COLOR"] != "0"
    stream = sys.stdout if stream is None else stream
    if not getattr(stream, "isatty", lambda: False)():
        return False
    if os.name == "nt":
        return _windows_ansi(stream)
    return True


def colorize(value, color: "str", enabled: "bool") -> "str":
    text = str(value)
    return f"\x1b[{COLORS[color]}m{text}\x1b[0m" if enabled else text


def banner(*, cli: "bool" = False, colors: "bool" = False) -> "str":
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


def print_banner(*, cli: "bool" = False, mode: "ColorMode" = "auto", stream=None) -> "None":
    stream = sys.stdout if stream is None else stream
    text = banner(cli=cli, colors=use_color(mode, stream))
    try:
        stream.write(text)
    except UnicodeEncodeError:
        # Python 3.6 has no TextIOWrapper.reconfigure; retain the Unicode logo
        # when its Windows output is redirected to a file or another process.
        if not hasattr(stream, "buffer"):
            raise
        stream.flush()
        stream.buffer.write(text.encode("utf-8"))
    stream.flush()
