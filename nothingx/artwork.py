from pathlib import Path
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen

from .models import model_info

COLORS = {"Orange": "orange", "Dark grey": "black", "Light grey": "white", "Blue": "blue"}
DEFAULT_COLOR = "blue"
ASSET_DIR = Path(__file__).parent / "assets" / "cmf-buds-pro-2"


def device_pixmap(color: str, part: str, model="B172") -> QPixmap:
    profile = model_info(model)
    family = profile.get("artwork", "generic")
    if family == "cmf-buds-pro-2" and part in ("left", "right", "case"):
        path = ASSET_DIR / f"{color if color in COLORS.values() else DEFAULT_COLOR}_{part}.png"
    else:
        path = ASSET_DIR.parent / "devices" / f"{family}_{part}.png"
    if path.is_file():
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            return pixmap
    pixmap = QPixmap(512, 512)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor("#a9acad"), 24, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    if part == "headphone":
        painter.drawArc(QRectF(95, 60, 322, 340), 0, 180 * 16)
        painter.setBrush(QColor("#292c2e"))
        painter.drawRoundedRect(QRectF(70, 240, 102, 190), 45, 45)
        painter.drawRoundedRect(QRectF(340, 240, 102, 190), 45, 45)
    else:
        painter.setBrush(QColor("#60666b"))
        painter.setPen(Qt.PenStyle.NoPen)
        if part == "case":
            painter.drawRoundedRect(QRectF(65, 120, 382, 275), 90, 90)
        else:
            painter.drawEllipse(QRectF(120, 72, 230, 230))
            painter.drawRoundedRect(QRectF(245, 180, 92, 265), 45, 45)
    painter.end()
    return pixmap


def device_thumbnail(color: str, part: str, size: int = 64, model="B172") -> QPixmap:
    return device_pixmap(color, part, model).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
