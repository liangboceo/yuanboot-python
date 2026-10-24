"""Build the framework and its matching CLI installer for PyPI and GitHub Releases."""

import argparse
import runpy
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=root / "dist")
    args = parser.parse_args()
    output = args.outdir.resolve()
    version = runpy.run_path(str(root / "src/yuanboot/_version.py"))["__version__"]
    subprocess.run([sys.executable, "-m", "build", "--outdir", str(output), str(root)], check=True)
    # A dependency-only distribution keeps one owner for the command and package resources.
    with tempfile.TemporaryDirectory(prefix="yuanbootctl-package-") as temporary:
        project = Path(temporary)
        metadata = (root / "packaging/cli/pyproject.toml.tpl").read_text(encoding="utf-8")
        (project / "pyproject.toml").write_text(
            metadata.replace("__VERSION__", version), encoding="utf-8"
        )
        shutil.copyfile(root / "packaging/cli/README.md", project / "README.md")
        shutil.copyfile(root / "LICENSE", project / "LICENSE")
        subprocess.run(
            [sys.executable, "-m", "build", "--outdir", str(output), str(project)], check=True
        )


if __name__ == "__main__":
    main()
