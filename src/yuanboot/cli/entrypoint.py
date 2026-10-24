"""Entry point for the standalone executable, including multiprocessing workers."""

import multiprocessing

from yuanboot.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
