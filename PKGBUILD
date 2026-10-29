pkgname=nothingx-linux
pkgver=0.1.2
pkgrel=1
pkgdesc='Unofficial native Qt companion for CMF Buds Pro 2'
arch=('any')
license=('MIT' 'LicenseRef-Nothing-Assets')
depends=('python' 'pyside6' 'bluez' 'bluez-utils')
options=('!strip' '!debug')
source=()
sha256sums=()

package() {
    install -dm755 "$pkgdir/usr/lib/nothingx-linux/nothingx"
    install -m644 "$startdir"/nothingx/*.py "$pkgdir/usr/lib/nothingx-linux/nothingx/"
    install -dm755 "$pkgdir/usr/lib/nothingx-linux/nothingx/assets/cmf-buds-pro-2"
    install -m644 "$startdir"/nothingx/assets/cmf-buds-pro-2/* "$pkgdir/usr/lib/nothingx-linux/nothingx/assets/cmf-buds-pro-2/"
    install -Dm755 "$startdir/packaging/nothingx-linux" "$pkgdir/usr/bin/nothingx-linux"
    install -Dm644 "$startdir/packaging/nothingx-linux.desktop" "$pkgdir/usr/share/applications/nothingx-linux.desktop"
    install -Dm644 "$startdir/nothingx/assets/cmf-buds-pro-2/blue_case.png" "$pkgdir/usr/share/icons/hicolor/512x512/apps/nothingx-linux.png"
    install -Dm644 "$startdir/LICENSE" "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
    install -Dm644 "$startdir/NOTICE" "$pkgdir/usr/share/licenses/$pkgname/NOTICE"
}
