"""Select a build backend compatible with the active Python interpreter."""

import sys

if sys.version_info >= (3, 8):
    from hatchling import build as backend
else:
    from setuptools import build_meta as backend

build_wheel = backend.build_wheel
build_sdist = backend.build_sdist
get_requires_for_build_wheel = backend.get_requires_for_build_wheel
get_requires_for_build_sdist = backend.get_requires_for_build_sdist
for hook in (
    "prepare_metadata_for_build_wheel",
    "build_editable",
    "get_requires_for_build_editable",
    "prepare_metadata_for_build_editable",
):
    if hasattr(backend, hook):
        globals()[hook] = getattr(backend, hook)
