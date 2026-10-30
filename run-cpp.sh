#!/bin/sh
set -eu
export NOTHINGX_BACKEND=cpp
exec "$(dirname -- "$0")/run.sh" "$@"
