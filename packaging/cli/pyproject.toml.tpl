[build-system]
requires = [
  "hatchling>=1.27,<2; python_version >= '3.8'",
  "setuptools>=59.6,<60; python_version < '3.8'",
  "wheel<0.38; python_version < '3.8'",
  "toml>=0.10.2,<1; python_version < '3.8'",
]
build-backend = "yuanboot_build"
backend-path = ["_build_backend"]

[project]
name = "yuanbootctl-python"
version = "__VERSION__"
description = "Project scaffolding, run and build tools for yuanboot-python"
readme = "README.md"
requires-python = ">=3.6.2"
license = "MIT"
authors = [{name = "jackson liang"}]
keywords = ["yuanboot", "cli", "fastapi", "scaffolding"]
classifiers = [
  "Programming Language :: Python :: 3",
  "Environment :: Console",
  "Topic :: Software Development :: Code Generators",
]
dependencies = ["yuanboot==__VERSION__"]

[project.optional-dependencies]
build = ["yuanboot[build]==__VERSION__"]
all = ["yuanboot[all]==__VERSION__"]
admin = ["yuanboot[admin]==__VERSION__"]

[project.urls]
Homepage = "https://github.com/liangboceo/yuanboot-python"
Documentation = "https://github.com/liangboceo/yuanboot-python/blob/master/docs/releases.md"
Repository = "https://github.com/liangboceo/yuanboot-python"
Issues = "https://github.com/liangboceo/yuanboot-python/issues"

[tool.hatch.build.targets.wheel]
bypass-selection = true
core-metadata-version = "2.4"

[tool.hatch.build.targets.sdist]
core-metadata-version = "2.4"
include = ["/pyproject.toml", "/README.md", "/LICENSE", "/_build_backend", "/setup.py", "/MANIFEST.in"]
