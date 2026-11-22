"""Source-install metadata for Python 3.6/3.7; shares pyproject.toml metadata."""

import runpy
from pathlib import Path

import toml
from setuptools import find_packages, setup

root = Path(__file__).resolve().parent
metadata = toml.load(str(root / "pyproject.toml"))["project"]
version = metadata.get("version")
if version is None:
    version = runpy.run_path(str(root / "src/yuanboot/_version.py"))["__version__"]
source = "src" if (root / "src/yuanboot").is_dir() else "."
packages = find_packages(where=source)
data = {}
for package in packages:
    folder = root / source / package.replace(".", "/")
    data[package] = [str(path.relative_to(folder)) for path in folder.rglob("*")
                     if path.is_file() and path.suffix != ".pyc" and "__pycache__" not in path.parts]
setup(
    name=metadata["name"], version=version, description=metadata["description"],
    long_description=(root / metadata["readme"]).read_text(encoding="utf-8"),
    long_description_content_type="text/markdown", author="jackson liang", license="MIT",
    python_requires=metadata["requires-python"], install_requires=metadata.get("dependencies", []),
    extras_require=metadata.get("optional-dependencies", {}), packages=packages,
    package_dir={"": source}, package_data=data, classifiers=metadata.get("classifiers", []),
    entry_points={"console_scripts": [name + "=" + target
                                     for name, target in metadata.get("scripts", {}).items()]},
    project_urls=metadata.get("urls", {}),
)
