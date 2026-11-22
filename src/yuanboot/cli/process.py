"""External process execution, signal forwarding and frozen runtime isolation."""

import os
import signal
import subprocess
import sys
from contextlib import contextmanager


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
