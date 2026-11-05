import math

from PySide6.QtCore import Qt, QRectF, QSize, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QPainterPath
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QCheckBox, QHBoxLayout, QPushButton, QSizePolicy, QWidget, QSlider

from .components import palette


class Switch(QCheckBox):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.position = 1.0 if self.isChecked() else 0.0
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(130)
        self.animation.valueChanged.connect(self.animate)
        self.toggled.connect(self.changed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(32)

    def setChecked(self, checked):
        super().setChecked(checked)
        if self.signalsBlocked() and hasattr(self, "animation"):
            self.animation.stop()
            self.position = float(checked)
            self.update()

    def sizeHint(self):
        return QSize(48 + (12 + self.fontMetrics().horizontalAdvance(self.text()) if self.text() else 0), 32)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def changed(self, checked):
        if not self.isVisible():
            self.position = float(checked)
            self.update()
            return
        self.animation.stop()
        self.animation.setStartValue(self.position)
        self.animation.setEndValue(float(checked))
        self.animation.start()

    def animate(self, value):
        self.position = float(value)
        self.update()

    def paintEvent(self, event):
        t = palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(.35)
        y = (self.height() - 26) / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t["accent"] if self.isChecked() else t["border"]))
        p.drawRoundedRect(QRectF(1, y, 46, 26), 13, 13)
        p.setBrush(QColor(t["ink"] if self.isChecked() else t["text"]))
        p.drawEllipse(QRectF(4 + 20 * self.position, y + 3, 20, 20))
        p.setPen(QColor(t["text"]))
        if self.text():
            p.drawText(QRectF(60, 0, max(0, self.width() - 60), self.height()), Qt.AlignmentFlag.AlignVCenter, self.text())
        if self.hasFocus():
            p.setPen(QPen(QColor(t["accent"]), 1, Qt.PenStyle.DotLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(0, y - 2, 48, 30), 15, 15)


class ModeButton(QAbstractButton):
    def __init__(self, title, icon="off", parent=None):
        super().__init__(parent)
        self.setText(title)
        self.icon_name = icon
        self.setCheckable(True)
        self.setAccessibleName(title)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumSize(84, 112)

    def sizeHint(self):
        return QSize(130, 116)

    def paintEvent(self, event):
        t = palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(.3)
        size = min(64, self.width() - 12)
        x = (self.width() - size) / 2
        p.setPen(QPen(QColor(t["accent"]), 1.5) if self.hasFocus() else Qt.PenStyle.NoPen)
        p.setBrush(QColor(t["accent"] if self.isChecked() else t["border"]))
        p.drawEllipse(QRectF(x, 6, size, size))
        color = QColor(t["ink"] if self.isChecked() else t["text"])
        p.setPen(QPen(color, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        cx, cy = self.width() / 2, 6 + size / 2
        if self.icon_name == "anc":
            p.drawArc(QRectF(cx - 12, cy - 12, 24, 24), -40 * 16, 260 * 16)
            p.drawEllipse(QRectF(cx - 2, cy - 2, 4, 4))
        elif self.icon_name in ("transparency", "spatial"):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(color)
            for i in range(8):
                angle = i * math.pi / 4
                radius = 2 if self.icon_name == "transparency" else 2.5
                p.drawEllipse(QRectF(cx + math.cos(angle) * 11 - radius, cy + math.sin(angle) * 11 - radius, radius * 2, radius * 2))
            if self.icon_name == "spatial":
                p.drawEllipse(QRectF(cx - 5, cy - 5, 10, 10))
        else:
            p.drawArc(QRectF(cx - 11, cy - 11, 22, 22), 25 * 16, 290 * 16)
            p.drawLine(int(cx - 12), int(cy - 13), int(cx + 12), int(cy + 13))
        p.setPen(QColor(t["text"] if self.isChecked() else t["muted"]))
        font = p.font()
        font.setPointSize(10)
        p.setFont(font)
        p.drawText(QRectF(0, size + 17, self.width(), 35), Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap, self.text())


class Segments(QWidget):
    selected = Signal(str)

    def __init__(self, values=(), parent=None):
        super().__init__(parent)
        self.box = QHBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(5)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        self.set_values(values)

    def set_values(self, values):
        if list(self.buttons) == list(values):
            return
        while self.box.count():
            item = self.box.takeAt(0)
            self.group.removeButton(item.widget())
            item.widget().deleteLater()
        self.buttons = {}
        for value in values:
            control = QPushButton(value)
            control.setCheckable(True)
            control.setMinimumWidth(40)
            control.setCursor(Qt.CursorShape.PointingHandCursor)
            control.clicked.connect(lambda checked=False, name=value: self.selected.emit(name))
            self.group.addButton(control)
            self.box.addWidget(control)
            self.buttons[value] = control

    def set_value(self, value):
        self.group.setExclusive(False)
        for name, control in self.buttons.items():
            control.setChecked(name == value)
        self.group.setExclusive(True)


class ThemeSwatch(QPushButton):
    def __init__(self, theme, parent=None):
        super().__init__(theme["name"], parent)
        self.theme = theme
        from .themes import DATA
        self.reference = QPixmap(str(DATA / "references" / theme["reference"])).scaled(400, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.setCheckable(True)
        self.setMinimumSize(138, 108)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(theme["name"] + " theme")

    def sizeHint(self):
        return QSize(180, 112)

    def minimumSizeHint(self):
        return QSize(138, 108)

    def paintEvent(self, event):
        t = self.theme
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(palette()["accent"] if self.isChecked() else palette()["border"]), 2 if self.isChecked() else 1))
        p.setBrush(QColor(t["background"]))
        p.drawRoundedRect(QRectF(2, 2, self.width() - 4, self.height() - 4), 18, 18)
        if not self.reference.isNull():
            area = QRectF(12, 10, self.width() - 24, 56)
            path = QPainterPath()
            path.addRoundedRect(area, 9, 9)
            p.save()
            p.setClipPath(path)
            image = self.reference.scaled(int(area.width()), int(area.height()), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            source = QRectF((image.width() - area.width()) / 2, (image.height() - area.height()) / 2, area.width(), area.height())
            p.drawPixmap(area, image, source)
            p.restore()
        p.setPen(QColor(t["text"]))
        p.drawText(QRectF(12, 70, self.width() - 24, 26), Qt.AlignmentFlag.AlignCenter, self.text() + ("  ✓" if self.isChecked() else ""))


class Slider(QSlider):
    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setMinimumHeight(32)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def value_at(self, position):
        ratio = max(0.0, min(1.0, (position.x() - 10) / max(1, self.width() - 20)))
        return round(self.minimum() + ratio * (self.maximum() - self.minimum()))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.setSliderDown(True)
            self.setValue(self.value_at(event.position()))
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown():
            self.setValue(self.value_at(event.position()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.isSliderDown():
            self.setValue(self.value_at(event.position()))
            self.setSliderDown(False)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()

    def paintEvent(self, event):
        t = palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(.3)
        y = self.height() / 2
        width = self.width() - 20
        ratio = (self.value() - self.minimum()) / max(1, self.maximum() - self.minimum())
        x = 10 + ratio * width
        p.setPen(QPen(QColor(t["border"]), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(10, int(y), self.width() - 10, int(y))
        p.setPen(QPen(QColor(t["accent"]), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(10, int(y), int(x), int(y))
        p.setPen(QPen(QColor(t["card"]), 2))
        p.setBrush(QColor(t["text"]))
        p.drawEllipse(QRectF(x - 9, y - 9, 18, 18))
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(t["accent"]), 1, Qt.PenStyle.DotLine))
            p.drawEllipse(QRectF(x - 13, y - 13, 26, 26))
