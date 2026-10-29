#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
if [ -n "${NOTHINGX_PYTHON:-}" ]; then
    exec "$NOTHINGX_PYTHON" -m nothingx "$@"
fi
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python -m nothingx "$@"
fi
exec python3 -m nothingx "$@"
