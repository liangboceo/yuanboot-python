"""Inspect both distributions to prevent local credentials/data leaking into releases."""

import tarfile
import zipfile
from pathlib import Path

artifacts = sorted(Path("dist").glob("yuanboot-*"))
assert any(path.suffix == ".whl" for path in artifacts), "Missing wheel"
assert any(path.name.endswith(".tar.gz") for path in artifacts), "Missing sdist"
for path in artifacts:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    else:
        with tarfile.open(path) as archive:
            names = archive.getnames()
    for name in names:
        parts = Path(name).parts
        assert not any(
            part.startswith(".env") or part in {".git", ".venv", "data", "reports"}
            for part in parts
        ), f"Private file in distribution: {name}"
        assert not name.endswith((".db", ".log", ".pyc")), f"Runtime file in distribution: {name}"
    assert any(name.endswith("templates/common/pyproject.toml.tpl") for name in names)
    print(f"Distribution verified: {path.name} ({len(names)} files)")
