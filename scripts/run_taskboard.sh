#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "$project_root/.venv/bin/yuanbootctl" run -p "$project_root/examples/taskboard" --host 127.0.0.1 "$@"
