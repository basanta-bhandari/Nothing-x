#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
NX_BACKEND=${1:-cpp}
case "$NX_BACKEND" in cpp|rust) ;; *) printf '%s\n' 'Usage: build-appimage.sh cpp|rust' >&2; exit 1 ;; esac
NX_ARCH=$(uname -m)
BUILD_DIR=${APPIMAGE_BUILD_DIR:-"$PROJECT_DIR/build/appimage-$NX_BACKEND"}
APP_DIR="$BUILD_DIR/NothingX.AppDir"
OUTPUT=${APPIMAGE_OUTPUT:-"$PROJECT_DIR/dist/NothingX-$NX_BACKEND-$NX_ARCH.AppImage"}
TOOL=${APPIMAGETOOL:-appimagetool}
PYTHON="$PROJECT_DIR/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    printf '%s\n' 'Run ./setup.sh first.' >&2
    exit 1
fi
mkdir -p "$BUILD_DIR" "$(dirname -- "$OUTPUT")"
cd "$PROJECT_DIR"
"$PYTHON" tools/build_backends.py --backend "$NX_BACKEND"
CFLAGS='-O2' "$PYTHON" setup.py build_ext --inplace
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/usr/bin"
"$PYTHON" tools/freeze.py --backend "$NX_BACKEND" --output "$APP_DIR/usr/bin"
install -m755 packaging/AppRun "$APP_DIR/AppRun"
install -m644 packaging/appimage.desktop "$APP_DIR/nothingx-linux.desktop"
install -m644 nothingx/assets/cmf-buds-pro-2/blue_case.png "$APP_DIR/nothingx-linux.png"
ln -sf nothingx-linux.png "$APP_DIR/.DirIcon"
if [ -n "${APPIMAGE_RUNTIME:-}" ]; then
    ARCH="$NX_ARCH" "$TOOL" --no-appstream --comp zstd --mksquashfs-opt=-processors --mksquashfs-opt=2 --runtime-file "$APPIMAGE_RUNTIME" "$APP_DIR" "$OUTPUT"
else
    ARCH="$NX_ARCH" "$TOOL" --no-appstream --comp zstd --mksquashfs-opt=-processors --mksquashfs-opt=2 "$APP_DIR" "$OUTPUT"
fi
chmod +x "$OUTPUT"
printf 'Built %s\n' "$OUTPUT"
