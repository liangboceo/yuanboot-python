"""Run or debug the application from the project root."""

import runpy


if __name__ == "__main__":
    runpy.run_module("__PACKAGE__.main", run_name="__main__")
