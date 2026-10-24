"""Install a built wheel in a fresh venv and exercise its packaged ctl templates."""

import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

wheel = (
    Path(sys.argv[1]).resolve()
    if len(sys.argv) > 1
    else max(Path("dist").glob("*.whl"), key=lambda path: path.stat().st_mtime).resolve()
)
with tempfile.TemporaryDirectory(prefix="yuanboot-wheel-") as directory:
    root = Path(directory)
    environment = root / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    executable = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def run(*arguments, cwd=root):
        result = subprocess.run(
            [str(executable), *arguments], cwd=cwd, capture_output=True, text=True, timeout=180
        )
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout

    run("-m", "pip", "install", str(wheel) + "[dev,all]")
    location = run("-c", "import yuanboot; print(yuanboot.__file__)").strip()
    assert str(environment) in location, location
    for template in ("mvc", "grpc"):
        name = "wheel_" + template
        run("-m", "yuanboot", "new", template, "-n", name, "-p", str(root))
        # Verify the business package accepts its generated Git direct dependency metadata.
        run("-m", "pip", "install", "--no-deps", "-e", ".", cwd=root / name)
        print(run("-m", "pytest", "-q", cwd=root / name).strip())
    report = {
        "wheel": wheel.name,
        "isolated_install": "passed",
        "generated_templates": {"mvc": "passed", "grpc": "passed"},
    }
    print(json.dumps(report, indent=2))
