"""Ensure a release tag agrees with the package's single version source."""

import re
import sys

from yuanboot import __version__

tag = sys.argv[1]
if not re.fullmatch(r"v\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", tag) or tag != "v" + __version__:
    raise SystemExit(f"Tag {tag!r} does not match package version v{__version__}")
print(f"Release version verified: {tag}")
