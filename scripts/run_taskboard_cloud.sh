#!/bin/sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ -f "$project_root/.env.integration" ]; then
    set -a
    . "$project_root/.env.integration"
    set +a
fi
exec "$project_root/.venv/bin/yuanbootctl" run -p "$project_root/examples/taskboard" \
    --profile cloud --host 0.0.0.0 --port 8080 "$@"
