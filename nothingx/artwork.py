
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

COLORS = {"Orange": "orange", "Dark grey": "black", "Light grey": "white", "Blue": "blue"}
DEFAULT_COLOR = "blue"
ASSET_DIR = Path(__file__).parent / "assets" / "cmf-buds-pro-2"


def device_pixmap(color: str, part: str) -> QPixmap:
    if color not in COLORS.values() or part not in ("left", "right", "case"):
        raise ValueError("Unknown product artwork")
    pixmap = QPixmap(str(ASSET_DIR / f"{color}_{part}.png"))
    if pixmap.isNull():
        raise RuntimeError(f"Missing device artwork: {color}_{part}.png. Reinstall the complete app package.")
    return pixmap


def device_thumbnail(color: str, part: str, size: int = 64) -> QPixmap:
    return device_pixmap(color, part).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
