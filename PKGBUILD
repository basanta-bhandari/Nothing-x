pkgname=nothingx-linux
pkgver=0.3.0
pkgrel=1
pkgdesc='Nothing X companion with a C++ backend and Cython Qt frontend'
arch=('x86_64')
license=('MIT' 'LicenseRef-Nothing-Assets')
depends=('python' 'pyside6' 'glib2' 'json-c' 'libpulse' 'bluez-libs' 'bluez' 'wireplumber')
makedepends=('cmake' 'ninja' 'cython' 'python-setuptools')
options=('!strip' '!debug')
source=()
sha256sums=()

build() {
    cmake -S "$startdir/native" -B "$startdir/build/native" -DCMAKE_BUILD_TYPE=Release
    cmake --build "$startdir/build/native" -j2
    install -Dm755 "$startdir/build/native/nothingx-core" "$startdir/nothingx/bin/nothingx-core"
    cd "$startdir"
    python setup.py build_ext --inplace
}

package() {
    install -dm755 "$pkgdir/usr/lib/nothingx-linux/nothingx"
    install -m644 "$startdir"/nothingx/*.py "$startdir"/nothingx/*.so "$pkgdir/usr/lib/nothingx-linux/nothingx/"
    install -Dm755 "$startdir/nothingx/bin/nothingx-core" "$pkgdir/usr/lib/nothingx-linux/nothingx/bin/nothingx-core"
    install -dm755 "$pkgdir/usr/lib/nothingx-linux/nothingx/assets/cmf-buds-pro-2"
    install -m644 "$startdir"/nothingx/assets/cmf-buds-pro-2/* "$pkgdir/usr/lib/nothingx-linux/nothingx/assets/cmf-buds-pro-2/"
    install -Dm755 "$startdir/packaging/nothingx-linux" "$pkgdir/usr/bin/nothingx-linux"
    install -Dm644 "$startdir/packaging/nothingx-linux.desktop" "$pkgdir/usr/share/applications/nothingx-linux.desktop"
    install -Dm644 "$startdir/nothingx/assets/cmf-buds-pro-2/blue_case.png" "$pkgdir/usr/share/icons/hicolor/512x512/apps/nothingx-linux.png"
    install -Dm644 "$startdir/LICENSE" "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
    install -Dm644 "$startdir/NOTICE" "$pkgdir/usr/share/licenses/$pkgname/NOTICE"
    install -dm755 "$pkgdir/usr/share/licenses/$pkgname/licenses"
    install -m644 "$startdir"/licenses/* "$pkgdir/usr/share/licenses/$pkgname/licenses/"
}
