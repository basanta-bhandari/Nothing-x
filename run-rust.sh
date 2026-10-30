#!/bin/sh
set -eu
export NOTHINGX_BACKEND=rust
exec "$(dirname -- "$0")/run.sh" "$@"
