#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
NX_CYTHON=1
while [ "$#" -gt 0 ]; do
    case "$1" in
        --no-cython) NX_CYTHON=0; shift ;;
        --backend) [ "${2:-}" = rust ] || { printf '%s\n' 'Only Rust is supported.' >&2; exit 1; }; shift 2 ;;
        *) printf 'Unknown option: %s\n' "$1" >&2; exit 1 ;;
    esac
done
command -v cargo >/dev/null 2>&1 || { printf '%s\n' 'Install Rust 1.85 or newer using rustup.' >&2; exit 1; }
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
.venv/bin/python tools/build_backends.py
if [ "$NX_CYTHON" = 1 ]; then CFLAGS=${CFLAGS:--O2} .venv/bin/python setup.py build_ext --inplace; fi
printf '%s\n' 'Start with ./run.sh. Package macOS with python packaging/build-macos.py.'
