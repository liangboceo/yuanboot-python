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
name = "__PROJECT__-server"
version = "0.1.0"
description = "An application built with yuanboot"
authors = [{name = "jackson liang"}]
readme = "README.md"
requires-python = ">=3.6.2"
dependencies = [__YUANBOOT_REQUIREMENT__]

[project.optional-dependencies]
dev = ["build>=0.7,<0.8; python_version < '3.8'", "build>=1.2; python_version >= '3.8'"]
components = [__YUANBOOT_COMPONENTS_REQUIREMENT__]

[tool.hatch.build.targets.wheel]
packages = ["__PACKAGE__"]

[tool.hatch.metadata]
allow-direct-references = true

[tool.yuanboot]
kind = "web"
app = "__PACKAGE__.main:app"
module = "__PACKAGE__.main"
