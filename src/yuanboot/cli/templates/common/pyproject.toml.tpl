[build-system]
requires = ["hatchling>=1.25"]
build-backend = "hatchling.build"

[project]
name = "__PROJECT__"
version = "0.1.0"
description = "An application built with yuanboot"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [__YUANBOOT_REQUIREMENT__]

[project.optional-dependencies]
dev = ["build>=1.2"]
components = [__YUANBOOT_COMPONENTS_REQUIREMENT__]

[tool.hatch.build.targets.wheel]
packages = ["__PACKAGE__"]

[tool.hatch.metadata]
allow-direct-references = true

[tool.yuanboot]
kind = "__KIND__"
app = "__PACKAGE__.main:app"
module = "__PACKAGE__.main"
