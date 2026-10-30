from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from .themes import theme_data

GLYPHS = {
    "N": ("10001", "11001", "11001", "10101", "10011", "10011", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    " ": ("00000",) * 7,
}


def palette():
    app = QApplication.instance()
    return theme_data(app.property("nothingx_theme") if app else None)


class DotLabel(QWidget):
    def __init__(self, text="NOTHING X", scale=2):
        super().__init__()
        self.text = text.upper()
        self.scale = scale
        self.setAccessibleName(text)
        self.setMinimumSize(self.sizeHint())

    def sizeHint(self):
        return QSize(len(self.text) * 6 * self.scale, 7 * self.scale + 4)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(palette()["text"]))
        for index, letter in enumerate(self.text):
            for y, line in enumerate(GLYPHS.get(letter, GLYPHS[" "])):
                for x, enabled in enumerate(line):
                    if enabled == "1":
                        painter.drawEllipse(QRectF((index * 6 + x) * self.scale, y * self.scale + 2, self.scale * .72, self.scale * .72))


class BatteryRing(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.level = None
        self.charging = False
        self.fresh = True
        self.setMinimumSize(76, 76)
        self.setMaximumSize(96, 96)
        self.setAccessibleName("Battery level")

    def set_value(self, data):
        self.level = data.get("level") if data else None
        self.charging = bool(data and data.get("charging"))
        self.fresh = bool(not data or data.get("available", True))
        self.setAccessibleName(f"{self.level}% battery" if self.level is not None else "Battery not reported")
        self.update()

    def paintEvent(self, event):
        colors = palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), self.height()) - 10
        bounds = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)
        painter.setPen(QPen(QColor(colors["border"]), 5))
        painter.drawEllipse(bounds)
        if self.level is not None:
            painter.setOpacity(1 if self.fresh else .5)
            painter.setPen(QPen(QColor(colors["accent"]), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(bounds, 90 * 16, -round(self.level * 360 * 16 / 100))
        painter.setOpacity(1)
        font = painter.font()
        font.setPointSize(13)
        font.setWeight(font.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(colors["text"]))
        painter.drawText(bounds, Qt.AlignmentFlag.AlignCenter, f"{self.level}%" if self.level is not None else "—")
