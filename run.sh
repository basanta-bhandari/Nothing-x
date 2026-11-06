#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
export NOTHINGX_BACKEND=rust
NX_SUFFIX=so
if [ "$(uname -s)" = Darwin ]; then NX_SUFFIX=dylib; export QT_EVENT_DISPATCHER_CORE_FOUNDATION=1; fi
NX_PYTHON=${NOTHINGX_PYTHON:-.venv/bin/python}
if [ ! -x "$NX_PYTHON" ] || [ ! -f "nothingx/bin/libnothingx_rust.$NX_SUFFIX" ]; then
    printf '%s\n' 'Run ./setup.sh first.' >&2
    exit 1
fi
exec "$NX_PYTHON" -m nothingx "$@"
