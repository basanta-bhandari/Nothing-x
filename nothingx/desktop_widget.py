import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout

from .artwork import device_pixmap
from .models import model_info
from .connection_help import connection_hint
from .widgets import Segments
from .preferences import read_preferences, save_preferences


class DesktopWidget(QWidget):
    dismissed = Signal()

    def __init__(self, controller):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnBottomHint)
        self.controller = controller
        self.setWindowTitle("Nothing X widget")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setFixedWidth(340)
        self.setObjectName("pageBody")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setObjectName("card")
        outer.addWidget(frame)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 20)
        header = QHBoxLayout()
        self.name = QLabel("Nothing X")
        self.name.setWordWrap(True)
        self.name.setObjectName("section")
        header.addWidget(self.name, 1)
        settings = QPushButton("Open")
        settings.clicked.connect(controller.restore)
        header.addWidget(settings)
        dismiss = QPushButton("×")
        dismiss.setAccessibleName("Hide desktop widget")
        dismiss.clicked.connect(self.close)
        header.addWidget(dismiss)
        layout.addLayout(header)
        self.art = QLabel()
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.art)
        self.battery = QLabel("Battery unavailable")
        self.battery.setWordWrap(True)
        self.battery.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.battery)
        self.status = QLabel("Disconnected")
        self.status.setObjectName("muted")
        layout.addWidget(self.status)
        self.connection_tip = QLabel(connection_hint(controller.display_model))
        self.connection_tip.setWordWrap(True)
        self.connection_tip.setObjectName("muted")
        layout.addWidget(self.connection_tip)
        self.modes = Segments()
        self.modes.selected.connect(lambda mode: controller.change("anc", mode))
        layout.addWidget(self.modes)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(controller.connect_device)
        layout.addWidget(self.connect_button)
        position = read_preferences().get("widget_position")
        if isinstance(position, list) and len(position) == 2 and all(type(v) is int for v in position):
            from PySide6.QtWidgets import QApplication
            if any(screen.availableGeometry().contains(*position) for screen in QApplication.screens()):
                self.move(*position)

    def render(self, state, phase):
        model = state.get("model", self.controller.display_model)
        profile = model_info(model)
        self.name.setText(profile["name"])
        part = "headphone" if profile["kind"] in ("headphones", "neckband") else "case"
        self.art.setPixmap(device_pixmap(self.controller.product_color, part, model).scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        names = {"left": "L", "right": "R", "case": "Case", "device": "Battery", "headphone": "Battery"}
        values = []
        for key, data in state.get("battery", {}).items():
            if data.get("level") is not None:
                suffix = " · last reported" if not data.get("available", True) else ""
                values.append(f"{names.get(key, key)} {data['level']}%{suffix}")
        self.battery.setText("   ".join(values) or "Battery unavailable")
        ready = phase in ("connected", "demo")
        self.connection_tip.setText(connection_hint(model))
        self.connection_tip.setVisible(not ready)
        self.status.setText({"connected": "Connected", "connecting": "Connecting…", "demo": "Demo"}.get(phase, "Disconnected"))
        modes = profile.get("anc_modes", [])
        strength = state.get("anc") if state.get("anc") not in ("Off", "Transparency") else next((v for v in ("Adaptive", "High", "Low") if v in modes), None)
        self.modes.set_values([mode for mode in (strength, "Transparency", "Off") if mode and mode in modes])
        self.modes.set_value(state.get("anc"))
        self.modes.setVisible("anc" in state)
        self.modes.setEnabled(ready and "anc" not in self.controller.pending)
        self.connect_button.setVisible(not ready)
        self.connect_button.setText("Cancel" if phase == "connecting" else "Connect")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.windowHandle():
            self.windowHandle().startSystemMove()
        super().mousePressEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "darwin" and QGuiApplication.platformName() == "cocoa":
            import ctypes
            import objc
            from AppKit import NSNormalWindowLevel, NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorStationary, NSWindowCollectionBehaviorIgnoresCycle
            view = objc.objc_object(c_void_p=ctypes.c_void_p(int(self.winId())))
            window = view.window()
            window.setLevel_(NSNormalWindowLevel - 1)
            window.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorStationary | NSWindowCollectionBehaviorIgnoresCycle)

    def closeEvent(self, event):
        save_preferences(widget_position=[self.x(), self.y()])
        self.dismissed.emit()
        event.accept()
