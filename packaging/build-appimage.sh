#!/bin/sh
set -eu
PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BUILD_DIR=${APPIMAGE_BUILD_DIR:-"$PROJECT_DIR/build/appimage"}
APP_DIR="$BUILD_DIR/NothingX.AppDir"
OUTPUT=${APPIMAGE_OUTPUT:-"$PROJECT_DIR/dist/NothingX-x86_64.AppImage"}
TOOL=${APPIMAGETOOL:-appimagetool}
PYTHON="$PROJECT_DIR/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    printf '%s\n' 'Run ./setup.sh first.' >&2
    exit 1
fi
if ! "$PYTHON" -c 'import PyInstaller' >/dev/null 2>&1; then
    "$PYTHON" -m pip install 'pyinstaller==6.22.3'
fi
mkdir -p "$BUILD_DIR" "$(dirname -- "$OUTPUT")"
cmake -S "$PROJECT_DIR/native" -B "$PROJECT_DIR/build/native" -DCMAKE_BUILD_TYPE=Release
cmake --build "$PROJECT_DIR/build/native" -j2
install -Dm755 "$PROJECT_DIR/build/native/nothingx-core" "$PROJECT_DIR/nothingx/bin/nothingx-core"
cd "$PROJECT_DIR"
CFLAGS='-O2 -march=x86-64 -mtune=generic' "$PYTHON" setup.py build_ext --inplace
rm -rf "$APP_DIR"
mkdir -p "$APP_DIR/usr/bin" "$BUILD_DIR/spec"
PYINSTALLER_CONFIG_DIR="$BUILD_DIR/pyinstaller-cache" "$PYTHON" -m PyInstaller --noconfirm --clean --onedir --name nothingx \
    --paths "$PROJECT_DIR" \
    --hidden-import nothingx.audio_ui --hidden-import nothingx.audio --hidden-import nothingx.core \
    --hidden-import nothingx.backend --hidden-import nothingx.protocol --hidden-import nothingx.artwork \
    --hidden-import PySide6.QtCore --hidden-import PySide6.QtGui --hidden-import PySide6.QtWidgets \
    --add-binary "$PROJECT_DIR/nothingx/bin/nothingx-core:nothingx/bin" \
    --add-data "$PROJECT_DIR/nothingx/assets/cmf-buds-pro-2:nothingx/assets/cmf-buds-pro-2" \
    --add-data "$PROJECT_DIR/LICENSE:." --add-data "$PROJECT_DIR/NOTICE:." \
    --add-data "$PROJECT_DIR/licenses:licenses" \
    --distpath "$APP_DIR/usr/bin" --workpath "$BUILD_DIR/pyinstaller" --specpath "$BUILD_DIR/spec" \
    "$PROJECT_DIR/packaging/appimage_entry.py"
install -m755 "$PROJECT_DIR/packaging/AppRun" "$APP_DIR/AppRun"
install -m644 "$PROJECT_DIR/packaging/appimage.desktop" "$APP_DIR/nothingx-linux.desktop"
install -m644 "$PROJECT_DIR/nothingx/assets/cmf-buds-pro-2/blue_case.png" "$APP_DIR/nothingx-linux.png"
ln -sf nothingx-linux.png "$APP_DIR/.DirIcon"
if [ -n "${APPIMAGE_RUNTIME:-}" ]; then
    ARCH=x86_64 "$TOOL" --no-appstream --comp zstd --mksquashfs-opt=-processors --mksquashfs-opt=2 --runtime-file "$APPIMAGE_RUNTIME" "$APP_DIR" "$OUTPUT"
else
    ARCH=x86_64 "$TOOL" --no-appstream --comp zstd --mksquashfs-opt=-processors --mksquashfs-opt=2 "$APP_DIR" "$OUTPUT"
fi
chmod +x "$OUTPUT"
printf 'Built %s\n' "$OUTPUT"
