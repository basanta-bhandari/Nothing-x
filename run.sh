#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
NX_BACKEND=${NOTHINGX_BACKEND:-cpp}
NX_EXPECT_BACKEND=0
for NX_ARG in "$@"; do
    if [ "$NX_EXPECT_BACKEND" = 1 ]; then NX_BACKEND=$NX_ARG; NX_EXPECT_BACKEND=0; fi
    case "$NX_ARG" in --backend) NX_EXPECT_BACKEND=1 ;; --backend=*) NX_BACKEND=${NX_ARG#--backend=} ;; esac
done
case "$NX_BACKEND" in cpp|rust) ;; *) printf '%s\n' 'Choose --backend cpp or --backend rust.' >&2; exit 1 ;; esac
NX_SUFFIX=so
if [ "$(uname -s)" = Darwin ]; then NX_SUFFIX=dylib; export QT_EVENT_DISPATCHER_CORE_FOUNDATION=1; fi
if [ -n "${NOTHINGX_PYTHON:-}" ]; then
    NX_PYTHON=$NOTHINGX_PYTHON
elif [ -x .venv/bin/python ]; then
    NX_PYTHON=.venv/bin/python
else
    printf 'Run ./setup.sh --backend %s first.\n' "$NX_BACKEND" >&2
    exit 1
fi
if [ ! -f "nothingx/bin/libnothingx_$NX_BACKEND.$NX_SUFFIX" ]; then
    printf 'Build this backend with ./setup.sh --backend %s\n' "$NX_BACKEND" >&2
    exit 1
fi
export NOTHINGX_BACKEND=$NX_BACKEND
exec "$NX_PYTHON" -m nothingx "$@"
