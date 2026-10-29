#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
.venv/bin/python -c 'from PySide6.QtCore import qVersion; from PySide6.QtWidgets import QApplication; print("Nothing X runtime ready: Qt " + qVersion())'
printf '%s\n' 'Start the app with ./run.sh'
