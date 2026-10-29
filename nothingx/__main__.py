import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Unofficial Nothing X desktop companion for CMF Buds Pro 2")
    parser.add_argument("--demo", action="store_true", help="Use a simulated device; no Bluetooth access")
    parser.add_argument("--screenshot", type=Path, help="Save a demo preview and exit (implies --demo)")
    args = parser.parse_args()
    try:
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QIcon
        from PySide6.QtWidgets import QApplication
    except ImportError as exc:
        missing = isinstance(exc, ModuleNotFoundError) and exc.name == "PySide6"
        reason = "PySide6 is not installed in this Python environment." if missing else "Qt could not be loaded. Its Python bindings and libraries may have different versions."
        parser.exit(1, f"{reason}\nPython: {sys.executable}\nImport error: {exc}\n"
                    "From the source folder, run ./setup.sh and then ./run.sh for a matching app-local Qt runtime.\n"
                    "For a system-package installation, update Qt and PySide6 together.\n")
    from .ui import MainWindow, STYLE
    from .artwork import ASSET_DIR
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Nothing X Linux")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(QIcon(str(ASSET_DIR / "blue_case.png")))
    window = MainWindow(demo=args.demo or bool(args.screenshot))
    if args.screenshot:
        window.resize(1140, 950)
    window.show()
    if args.screenshot:
        def capture():
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(args.screenshot)):
                print("Could not save screenshot", file=sys.stderr)
            window.quit()
        QTimer.singleShot(700, capture)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
