"""Build a native, self-contained CLI and package it for a GitHub Release."""

import argparse
import platform
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from yuanboot import __version__

root = Path(__file__).resolve().parent.parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=root / "dist")
args = parser.parse_args()
output = args.output.resolve()
system = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}[platform.system()]
machine = platform.machine().lower()
architecture = {"x86_64": "amd64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64"}[machine]
subprocess.run(
    [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--distpath",
        str(output / "bin"),
        "--workpath",
        str(root / "build/pyinstaller"),
        str(root / "packaging/yuanbootctl-python.spec"),
    ],
    cwd=root,
    check=True,
)
executable = (
    output / "bin" / ("yuanbootctl-python.exe" if system == "windows" else "yuanbootctl-python")
)
name = f"yuanbootctl-python_{__version__}_{system}_{architecture}"
if system == "windows":
    archive = output / (name + ".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.write(executable, executable.name)
        package.write(root / "LICENSE", "LICENSE")
else:
    archive = output / (name + ".tar.gz")
    with tarfile.open(archive, "w:gz") as package:
        package.add(executable, arcname=executable.name)
        package.add(root / "LICENSE", arcname="LICENSE")
print(f"Release binary: {archive}")
