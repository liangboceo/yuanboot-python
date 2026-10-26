[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[project]
name = "yuanbootctl-python"
version = "__VERSION__"
description = "Project scaffolding, run and build tools for yuanboot-python"
readme = "README.md"
requires-python = ">=3.11"
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
include = ["/pyproject.toml", "/README.md", "/LICENSE"]
