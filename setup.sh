#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
NX_BACKEND=${NOTHINGX_BACKEND:-cpp}
NX_CYTHON=1
while [ "$#" -gt 0 ]; do
    case "$1" in
        --backend) NX_BACKEND=${2:?Choose cpp, rust or all}; shift 2 ;;
        --no-cython) NX_CYTHON=0; shift ;;
        *) printf 'Unknown setup option: %s\n' "$1" >&2; exit 1 ;;
    esac
done
case "$NX_BACKEND" in cpp|rust|all) ;; *) printf '%s\n' 'Choose cpp, rust or all.' >&2; exit 1 ;; esac
if ! command -v python3 >/dev/null 2>&1; then
    printf '%s\n' 'Install Python 3.11 or newer.' >&2
    exit 1
fi
if [ "$NX_BACKEND" != rust ]; then
    for tool in cmake c++ pkg-config; do
        if ! command -v "$tool" >/dev/null 2>&1; then
            printf '%s\n' 'C++ build dependencies: cmake, a C++20 compiler, pkg-config and json-c.' >&2
            exit 1
        fi
    done
fi
if [ "$NX_BACKEND" != cpp ] && ! command -v cargo >/dev/null 2>&1; then
    printf '%s\n' 'Install Rust 1.85 or newer using rustup.' >&2
    exit 1
fi
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
.venv/bin/python tools/build_backends.py --backend "$NX_BACKEND"
if [ "$NX_CYTHON" = 1 ]; then
    CFLAGS=${CFLAGS:--O2} .venv/bin/python setup.py build_ext --inplace
fi
if [ "$(uname -s)" = Darwin ]; then
    .venv/bin/python -m pip install -r requirements-build.txt
    for NX_BUILD in cpp rust; do
        if [ "$NX_BACKEND" = all ] || [ "$NX_BACKEND" = "$NX_BUILD" ]; then
            .venv/bin/python packaging/build-macos.py --backend "$NX_BUILD" --distribution manual --no-dmg
        fi
    done
fi
.venv/bin/python -c 'from PySide6.QtCore import qVersion; from PySide6.QtBluetooth import QBluetoothSocket; print("Nothing X runtime ready: Qt " + qVersion())'
if [ "$NX_BACKEND" = all ]; then
    printf '%s\n' 'Start with ./run-cpp.sh or ./run-rust.sh'
else
    printf 'Start with ./run.sh --backend %s\n' "$NX_BACKEND"
fi
