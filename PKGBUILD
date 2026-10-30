pkgname=('nothingx-cpp' 'nothingx-rust')
pkgbase=nothingx
pkgver=0.4.0
pkgrel=1
pkgdesc='Nothing and CMF audio controls with a shared Qt frontend'
arch=('x86_64' 'aarch64')
url='https://github.com/basanta-bhandari/Nothing-x'
license=('MIT' 'LicenseRef-Nothing-Assets')
depends=('python' 'pyside6' 'json-c' 'bluez' 'bluez-utils' 'libpulse' 'wireplumber')
makedepends=('cmake' 'ninja' 'cython' 'python-setuptools' 'rust')
options=('!strip' '!debug')
source=()
sha256sums=()

build() {
    cd "$startdir"
    python tools/build_backends.py --backend all
    python setup.py build_ext --inplace
}

_package() {
    local backend=$1
    local appdir="$pkgdir/usr/lib/nothingx-$backend"
    install -dm755 "$appdir/nothingx/bin" "$appdir/nothingx/assets"
    install -m644 "$startdir"/nothingx/*.py "$startdir"/nothingx/*.so "$appdir/nothingx/"
    install -m755 "$startdir/nothingx/bin/libnothingx_$backend.so" "$appdir/nothingx/bin/"
    cp -r "$startdir/nothingx/assets/." "$appdir/nothingx/assets/"
    printf '{"backend":"%s","distribution":"manual","managed":"pacman","version":"%s"}\n' "$backend" "$pkgver" > "$appdir/nothingx/assets/build.json"
    install -dm755 "$pkgdir/usr/bin" "$pkgdir/usr/share/applications"
    printf '#!/bin/sh\ncd /usr/lib/nothingx-%s\nexport NOTHINGX_BACKEND=%s\nexec /usr/bin/python -m nothingx "$@"\n' "$backend" "$backend" > "$pkgdir/usr/bin/nothingx-$backend"
    chmod 755 "$pkgdir/usr/bin/nothingx-$backend"
    printf '[Desktop Entry]\nType=Application\nName=Nothing X (%s)\nExec=nothingx-%s\nIcon=/usr/lib/nothingx-%s/nothingx/assets/cmf-buds-pro-2/blue_case.png\nTerminal=false\nCategories=AudioVideo;Audio;Settings;\nKeywords=Nothing;CMF;Buds;Headphones;\n' "$backend" "$backend" "$backend" > "$pkgdir/usr/share/applications/io.github.basanta_bhandari.NothingX.$backend.desktop"
    install -Dm644 "$startdir/LICENSE" "$pkgdir/usr/share/licenses/nothingx-$backend/LICENSE"
    install -m644 "$startdir/NOTICE" "$pkgdir/usr/share/licenses/nothingx-$backend/NOTICE"
    cp -r "$startdir/licenses" "$pkgdir/usr/share/licenses/nothingx-$backend/"
}

package_nothingx-cpp() { _package cpp; }
package_nothingx-rust() { _package rust; }
