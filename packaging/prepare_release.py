"""Set the package version for a manually requested Actions release."""

import re
import sys
from pathlib import Path


def prepare_release(version: str, root: Path) -> str:
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", version):
        raise ValueError("Version must look like 0.1.3 or 0.2.0rc1, without a v prefix")
    version_file = root / "src/yuanboot/_version.py"
    version_file.write_text(f'__version__ = "{version}"\n', encoding="utf-8")
    return "v" + version


if __name__ == "__main__":
    print(prepare_release(sys.argv[1], Path(__file__).resolve().parent.parent))
