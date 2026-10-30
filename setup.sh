#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
for tool in cmake c++ pkg-config; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf '%s\n' 'Build dependencies: sudo pacman -S --needed base-devel cmake ninja glib2 json-c libpulse bluez-libs' >&2
        exit 1
    fi
done
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
cmake -S native -B build/native -DCMAKE_BUILD_TYPE=Release
cmake --build build/native -j2
install -Dm755 build/native/nothingx-core nothingx/bin/nothingx-core
.venv/bin/python setup.py build_ext --inplace
.venv/bin/python -c 'from PySide6.QtCore import qVersion; from PySide6.QtWidgets import QApplication; print("Nothing X runtime ready: Qt " + qVersion())'
printf '%s\n' 'Start the app with ./run.sh'
