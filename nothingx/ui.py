from PySide6.QtCore import Qt, QSettings, QTimer, QRectF, QPointF, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPen
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QPushButton, QCheckBox, QComboBox, QSpinBox, QSlider, QHBoxLayout, QVBoxLayout,
    QScrollArea, QStackedWidget, QLineEdit, QMessageBox, QSystemTrayIcon,
    QMenu, QSizePolicy)

from .backend import Worker, MAC
from .protocol import ANC, EQ
from .artwork import COLORS, DEFAULT_COLOR, device_pixmap, device_thumbnail

ACCENT = "#ff6432"
STYLE = """
QWidget { background: #101112; color: #f1f1ed; font-family: 'Inter', 'Noto Sans', sans-serif; font-size: 14px; }
QMainWindow { background: #101112; }
QFrame#sidebar { background: #171819; border-right: 1px solid #2b2c2d; }
QFrame#card { background: #1c1d1f; border: 1px solid #303133; border-radius: 16px; }
QLabel, QCheckBox { background: transparent; }
QLabel#muted { color: #969b9e; }
QLabel#eyebrow { color: #ff7950; font-family: monospace; font-size: 11px; font-weight: 600; }
QLabel#title { font-size: 31px; font-weight: 650; }
QLabel#section { font-size: 18px; font-weight: 600; }
QLabel#banner { padding: 12px 15px; background: #212629; border: 1px solid #3b4449; border-radius: 9px; }
QPushButton { background: #292b2e; border: 1px solid #3a3c3e; padding: 10px 16px; border-radius: 9px; font-weight: 550; }
QPushButton:hover { background: #36383a; border-color: #666; }
QPushButton:pressed { background: #45474a; }
QPushButton:checked { background: #f2653c; border-color: #f2653c; color: #111; }
QPushButton:disabled { color: #626669; border-color: #303235; background: #202224; }
QPushButton#primary { background: #ff6432; color: #101112; border: 0; }
QPushButton#primary:hover { background: #ff8057; }
QPushButton#nav { text-align: left; padding: 14px; border: 0; background: transparent; color: #a5a9aa; }
QPushButton#nav:checked { background: #2b2522; color: #ff825b; }
QPushButton#nav:hover { background: #262729; }
QComboBox, QLineEdit, QSpinBox { background: #151618; border: 1px solid #45474a; border-radius: 7px; padding: 9px; min-height: 21px; selection-background-color: #ff6432; }
QComboBox:disabled { color: #666; border-color: #303235; }
QComboBox QAbstractItemView { background: #252729; selection-background-color: #86472e; padding: 5px; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 38px; height: 22px; border-radius: 11px; background: #44484a; border: 1px solid #5c6063; }
QCheckBox::indicator:checked { background: #ff6432; border-color: #ff6432; }
QCheckBox::indicator:disabled { background: #292b2d; border-color: #36383a; }
QSlider::groove:horizontal { background: #45484a; height: 5px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #ff6432; border-radius: 2px; }
QSlider::handle:horizontal { background: #f3f1ea; border: 3px solid #ff6432; width: 15px; height: 15px; margin: -8px 0; border-radius: 10px; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: #151618; width: 8px; }
QScrollBar::handle:vertical { background: #44474a; border-radius: 4px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background: #303235; color: #eee; border: 1px solid #666; padding: 6px; }
"""


def label(text, role=None, wrap=False):
    w = QLabel(text)
    if role:
        w.setObjectName(role)
    w.setWordWrap(wrap)
    return w


def button(text, callback=None, primary=False):
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        b.setObjectName("primary")
    if callback:
        b.clicked.connect(callback)
    return b


def card(title=None, subtitle=None):
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(23, 21, 23, 23)
    layout.setSpacing(15)
    if title:
        layout.addWidget(label(title, "section"))
    if subtitle:
        layout.addWidget(label(subtitle, "muted", True))
    return frame, layout


class BudsArt(QWidget):

    def __init__(self, color=DEFAULT_COLOR):
        super().__init__()
        self.setMinimumSize(290, 175)
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.set_color(color)

    def set_color(self, color):
        self.color = color
        self.images = {part: device_pixmap(color, part) for part in ("left", "right", "case")}
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(self.width() / 420, self.height() / 200)
        p.translate((self.width() - 420 * scale) / 2, (self.height() - 200 * scale) / 2)
        p.scale(scale, scale)
        p.setPen(Qt.PenStyle.NoPen)
        for y in range(10, 200, 13):
            for x in range(8, 420, 13):
                p.setBrush(QColor("#333334"))
                p.drawEllipse(QPointF(x, y), 0.8, 0.8)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for part, x in (("left", 20), ("right", 130)):
            p.drawPixmap(QRectF(x, 24, 90, 148), self.images[part], QRectF(127, 44, 258, 424))
        p.drawPixmap(QRectF(250, 16, 165, 165), self.images["case"], QRectF(64, 64, 384, 384))
        p.setPen(QColor("#969b9e"))
        for text, x, width in (("L", 20, 90), ("R", 130, 90), ("CASE", 250, 165)):
            p.drawText(QRectF(x, 180, width, 20), Qt.AlignmentFlag.AlignCenter, text)
        p.end()


class BatteryTile(QFrame):
    def __init__(self, title, mark, part, color):
        super().__init__()
        self.setObjectName("card")
        box = QVBoxLayout(self)
        box.setContentsMargins(20, 15, 20, 17)
        top = QHBoxLayout()
        top.addWidget(label(title, "muted"))
        top.addStretch()
        top.addWidget(label(mark, "eyebrow"))
        box.addLayout(top)
        self.value = label("—")
        self.value.setStyleSheet("font-size: 29px; font-weight: 600; background: transparent;")
        self.detail = label("Waiting for device", "muted")
        middle = QHBoxLayout()
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(58, 58)
        self.part = part
        self.set_color(color)
        middle.addWidget(self.thumbnail)
        stats = QVBoxLayout()
        stats.setSpacing(1)
        stats.addWidget(self.value)
        stats.addWidget(self.detail)
        middle.addLayout(stats, 1)
        box.addLayout(middle)

    def set_color(self, color):
        self.thumbnail.setPixmap(device_thumbnail(color, self.part, 58))

    def update_value(self, data):
        self.value.setText(f'{data["level"]}%' if data else "—")
        self.detail.setText(("Charging" if data["charging"] else "Battery level") if data else "Not reported")


class Switch(QCheckBox):
    def sizeHint(self):
        return QSize(40 + (10 + self.fontMetrics().horizontalAdvance(self.text()) if self.text() else 0), 26)

    def hitButton(self, pos):
        return self.rect().contains(pos)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        y = (self.height() - 22) / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(ACCENT if self.isChecked() else "#4b4e51"))
        p.drawRoundedRect(QRectF(0, y, 38, 22), 11, 11)
        p.setBrush(QColor("#141414" if self.isChecked() else "#d5d7d8"))
        p.drawEllipse(QRectF(19 if self.isChecked() else 3, y + 3, 16, 16))
        p.setPen(QColor("#f1f1ed"))
        p.drawText(QRectF(49, 0, max(0, self.width() - 49), self.height()), Qt.AlignmentFlag.AlignVCenter, self.text())
        if self.hasFocus():
            p.setPen(QPen(QColor("#ffad7c"), 1, Qt.PenStyle.DotLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(0, y - 2, 40, 26), 12, 12)
        p.end()


class MainWindow(QMainWindow):
    def __init__(self, demo=False):
        super().__init__()
        self.setWindowTitle("Nothing X · Linux")
        self.resize(1140, 850)
        self.setMinimumSize(920, 680)
        self.settings = QSettings("NothingXLinux", "NothingXLinux")
        self.product_color = str(self.settings.value("product_color", DEFAULT_COLOR))
        if self.product_color not in COLORS.values():
            self.product_color = DEFAULT_COLOR
        self.state = {}
        self.pending = set()
        self.connection = "disconnected"
        self.controls = {}
        self._closing = False
        self.worker = Worker(self)
        self.worker.state_changed.connect(self.render)
        self.worker.status.connect(self.on_status)
        self.worker.message.connect(self.show_message)
        self.worker.devices.connect(self.on_devices)
        self.worker.completed.connect(self.on_completed)
        self._build()
        self._tray()
        self.worker.start()
        if demo:
            self.worker.submit("demo")
        else:
            self.worker.submit("devices")
        self.render({})
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(30000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        base = QHBoxLayout(root)
        base.setContentsMargins(0, 0, 0, 0)
        base.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(205)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(19, 30, 19, 22)
        brand = label("NOTHING (X)")
        brand.setStyleSheet("font-family: monospace; font-size: 20px; font-weight: bold; background: transparent;")
        side.addWidget(brand)
        side.addWidget(label("UNOFFICIAL / LINUX", "eyebrow"))
        side.addSpacing(38)
        self.pages = QStackedWidget()
        self.nav = []
        for index, text in enumerate(["◉   Overview", "≋   Sound", "⌘   Device"]):
            b = button(text, lambda checked=False, i=index: self.navigate(i))
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setChecked(index == 0)
            self.nav.append(b)
            side.addWidget(b)
        side.addStretch()
        self.side_status = label("○  Disconnected", "muted", True)
        side.addWidget(self.side_status)
        side.addSpacing(13)
        self.demo_button = button("Explore demo", self.start_demo)
        side.addWidget(self.demo_button)
        side.addWidget(label("Built for CMF\nBuds Pro 2 · B172 / B187", "muted"))
        base.addWidget(sidebar)
        main = QWidget()
        content = QVBoxLayout(main)
        content.setContentsMargins(30, 25, 30, 23)
        content.setSpacing(16)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.addWidget(label("YOUR LISTENING SPACE", "eyebrow"))
        self.page_title = label("Overview", "title")
        heading.addWidget(self.page_title)
        header.addLayout(heading)
        header.addStretch()
        self.refresh_button = button("↻  Refresh", self.refresh)
        header.addWidget(self.refresh_button)
        content.addLayout(header)
        self.banner = label("Pair your earbuds in your desktop’s Bluetooth settings, then connect below.", "banner", True)
        content.addWidget(self.banner)
        connection, row = card()
        row.setContentsMargins(15, 13, 15, 13)
        line = QHBoxLayout()
        self.device_select = QComboBox()
        self.device_select.addItem("Select paired earbuds…", "")
        self.device_select.setMinimumWidth(180)
        self.device_select.setToolTip("Paired Bluetooth devices")
        self.device_select.currentIndexChanged.connect(self.select_device)
        self.address = QLineEdit(str(self.settings.value("address", "")))
        self.address.setPlaceholderText("AA:BB:CC:DD:EE:FF")
        self.address.setAccessibleName("Bluetooth device address")
        self.address.setMinimumWidth(165)
        self.address.returnPressed.connect(self.connect_device)
        self.connect_button = button("Connect", self.connect_device, True)
        self.reload_button = button("↻", lambda: self.worker.submit("devices"))
        self.reload_button.setToolTip("Reload paired devices")
        line.addWidget(self.device_select, 2)
        line.addWidget(self.address, 2)
        line.addWidget(self.reload_button)
        line.addWidget(self.connect_button)
        row.addLayout(line)
        content.addWidget(connection)
        content.addWidget(self.pages, 1)
        base.addWidget(main, 1)
        self.overview()
        self.sound_page()
        self.device_page()
        footer = QHBoxLayout()
        self.status_text = label("Ready when you are.", "muted")
        footer.addWidget(self.status_text, 1)
        footer.addWidget(label("LOCAL BLUETOOTH · NO ACCOUNT", "eyebrow"))
        content.addLayout(footer)

    def page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.setSpacing(16)
        scroll.setWidget(body)
        self.pages.addWidget(scroll)
        return layout

    def overview(self):
        box = self.page()
        hero, h = card()
        hero.setMinimumHeight(190)
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.addWidget(label("CMF BY NOTHING", "eyebrow"))
        name = label("Buds Pro 2")
        name.setStyleSheet("font-size: 33px; font-weight: 650; background: transparent;")
        text.addWidget(name)
        self.hero_status = label("Make yourself heard.\nMake the world quieter.", "muted", True)
        text.addWidget(self.hero_status)
        text.addStretch()
        appearance = QHBoxLayout()
        appearance.addWidget(label("Colour", "muted"))
        self.color_select = QComboBox()
        self.color_select.setAccessibleName("Earbud and case colour")
        self.color_select.setToolTip("Match the product artwork to your earbuds")
        for name, value in COLORS.items():
            self.color_select.addItem(name, value)
        self.color_select.setCurrentIndex(self.color_select.findData(self.product_color))
        self.color_select.currentIndexChanged.connect(self.change_color)
        appearance.addWidget(self.color_select)
        appearance.addStretch()
        text.addLayout(appearance)
        row.addLayout(text, 1)
        self.product_art = BudsArt(self.product_color)
        row.addWidget(self.product_art, 1)
        h.addLayout(row)
        box.addWidget(hero)
        batteries = QHBoxLayout()
        self.batteries = {}
        for key, title, mark in [("left", "Left earbud", "L"), ("right", "Right earbud", "R"), ("case", "Charging case", "C")]:
            tile = BatteryTile(title, mark, key, self.product_color)
            self.batteries[key] = tile
            batteries.addWidget(tile)
        box.addLayout(batteries)
        noise, n = card("Tune out. Tune in.", "Choose how much of the outside world comes through.")
        self.anc_buttons = {}
        modes = QHBoxLayout()
        for title, value in [("Noise cancellation", "Adaptive"), ("Transparency", "Transparency"), ("Off", "Off")]:
            b = button(title, lambda checked=False, v=value: self.change("anc", v))
            b.setCheckable(True)
            modes.addWidget(b)
            self.anc_buttons[title] = b
        n.addLayout(modes)
        strength_row = QHBoxLayout()
        strength_row.addWidget(label("Cancellation strength", "muted"))
        strength_row.addStretch()
        self.anc_level = QComboBox()
        self.anc_level.addItems(["Adaptive", "High", "Mid", "Low"])
        self.anc_level.activated.connect(lambda: self.change("anc", self.anc_level.currentText()))
        strength_row.addWidget(self.anc_level)
        n.addLayout(strength_row)
        box.addWidget(noise)
        box.addStretch()

    def change_color(self):
        color = self.color_select.currentData()
        if color not in COLORS.values():
            return
        self.product_color = color
        self.settings.setValue("product_color", color)
        self.product_art.set_color(color)
        for tile in self.batteries.values():
            tile.set_color(color)

    def sound_page(self):
        box = self.page()
        eq_card, e = card("Your sound, your way.", "EQ presets are processed on the earbuds and follow you across devices.")
        self.eq_select = QComboBox()
        self.eq_select.addItem("Waiting for device")
        self.eq_select.addItems(EQ)
        self.eq_select.activated.connect(lambda: self.change("eq", self.eq_select.currentText()))
        self.controls["eq"] = self.eq_select
        e.addWidget(self.eq_select)
        e.addWidget(label("Custom EQ and gesture remapping are not available in this version.", "muted", True))
        box.addWidget(eq_card)
        bass_card, b = card("Ultra Bass", "Add extra weight to the low end.")
        self.bass_toggle = Switch("Enable Ultra Bass")
        self.bass_toggle.clicked.connect(self.bass_changed)
        b.addWidget(self.bass_toggle)
        bass_line = QHBoxLayout()
        self.bass_slider = QSlider(Qt.Orientation.Horizontal)
        self.bass_slider.setRange(0, 10)
        self.bass_slider.setAccessibleName("Ultra Bass level")
        self.bass_slider.valueChanged.connect(lambda v: self.bass_value.setText(f"{v / 2:g} / 5"))
        self.bass_slider.sliderReleased.connect(self.bass_changed)
        self.bass_slider.actionTriggered.connect(self.bass_keyboard)
        self.bass_value = label("—", "eyebrow")
        bass_line.addWidget(self.bass_slider, 1)
        bass_line.addWidget(self.bass_value)
        b.addLayout(bass_line)
        box.addWidget(bass_card)
        extras, x = card("A different dimension")
        self.toggle_row(x, "spatial", "Spatial audio", "A wider, more immersive sound stage.")
        self.toggle_row(x, "low_latency", "Low latency mode", "Reduce audio delay for games and video.")
        box.addWidget(extras)
        box.addStretch()

    def toggle_row(self, box, key, title, detail):
        row = QHBoxLayout()
        words = QVBoxLayout()
        words.addWidget(label(title))
        words.addWidget(label(detail, "muted", True))
        row.addLayout(words, 1)
        toggle = Switch()
        toggle.setAccessibleName(title)
        toggle.setToolTip("Waiting for a device response")
        toggle.clicked.connect(lambda value, k=key: self.change(k, value))
        row.addWidget(toggle)
        box.addLayout(row)
        self.controls[key] = toggle

    def device_page(self):
        box = self.page()
        settings, s = card("Made for your everyday")
        self.toggle_row(s, "in_ear", "In-ear detection", "Pause automatically when you remove an earbud.")
        self.toggle_row(s, "dual", "Dual connection", "Keep two devices connected. Availability can depend on LDAC.")
        codec_line = QHBoxLayout()
        codec_text = QVBoxLayout()
        codec_text.addWidget(label("High-resolution audio"))
        codec_text.addWidget(label("Changing codec may reconnect the earbuds.\nSelect LDAC in your desktop audio settings afterward.", "muted", True))
        codec_line.addLayout(codec_text, 1)
        self.codec_select = QComboBox()
        self.codec_select.addItem("Waiting for device", -1)
        self.codec_select.addItem("Standard · AAC / SBC", 0)
        self.codec_select.addItem("LDAC", 2)
        self.codec_select.activated.connect(self.change_codec)
        self.controls["codec"] = self.codec_select
        codec_line.addWidget(self.codec_select)
        s.addLayout(codec_line)
        box.addWidget(settings)
        find, f = card("Find my earbuds", "Remove the earbuds from your ears before playing a locator sound.")
        locator = QHBoxLayout()
        self.find_buttons = []
        for title, side in [("Ring left", 2), ("Ring right", 3)]:
            b = button(title, lambda checked=False, v=side: self.find_bud(v))
            locator.addWidget(b)
            self.find_buttons.append(b)
        self.stop_button = button("Stop ringing", self.stop_ringing)
        locator.addWidget(self.stop_button)
        f.addLayout(locator)
        box.addWidget(find)
        info, i = card("Connection & device")
        self.info = label("Model —   ·   Firmware —", "muted", True)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        i.addWidget(self.info)
        channel_line = QHBoxLayout()
        channel_line.addWidget(label("RFCOMM channel", "muted"))
        self.channel = QSpinBox()
        self.channel.setRange(0, 30)
        self.channel.setSpecialValueText("Auto")
        self.channel.setValue(int(self.settings.value("channel", 0)))
        self.channel.setToolTip("Auto finds the control service. Channels 15 and 16 are common. Takes effect at next connection.")
        channel_line.addWidget(self.channel)
        channel_line.addStretch()
        i.addLayout(channel_line)
        self.minimize_tray = Switch("Keep running in the tray when closing the window")
        self.minimize_tray.setChecked(self.settings.value("tray", False, type=bool))
        i.addWidget(self.minimize_tray)
        i.addWidget(label("Firmware updates remain available through the official Nothing X mobile app.", "muted", True))
        box.addWidget(info)
        box.addStretch()

    def _tray(self):
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self)
            self.tray.setIcon(self.windowIcon() if not self.windowIcon().isNull() else QIcon.fromTheme("audio-headphones"))
            self.tray.setToolTip("Nothing X · Linux")
            menu = QMenu()
            menu.addAction("Open Nothing X", self.restore)
            menu.addAction("Disconnect controls", lambda: self.worker.submit("disconnect"))
            menu.addSeparator()
            menu.addAction("Quit", self.quit)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.restore() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
            self.tray.show()

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        self.page_title.setText(["Overview", "Sound", "Device"][index])
        for i, b in enumerate(self.nav):
            b.setChecked(i == index)

    def on_devices(self, devices):
        current = self.address.text()
        self.device_select.blockSignals(True)
        self.device_select.clear()
        self.device_select.addItem("Select paired earbuds…", "")
        for address, name in devices:
            self.device_select.addItem(name, address)
        self.device_select.blockSignals(False)
        if current:
            idx = self.device_select.findData(current)
            self.device_select.setCurrentIndex(max(0, idx))
        elif devices:
            matches = [(a, n) for a, n in devices if "cmf" in n.lower() and "pro 2" in n.lower()]
            if len(matches) == 1:
                self.device_select.setCurrentIndex(self.device_select.findData(matches[0][0]))
        if not devices:
            self.show_message("No paired devices found. Pair the buds in Bluetooth settings, then reload the list. You can also enter their address directly.", False)

    def select_device(self):
        address = self.device_select.currentData()
        if address:
            self.address.setText(address)

    def connect_device(self):
        if self.connection == "connecting":
            self.connect_button.setEnabled(False)
            self.worker.submit("disconnect")
            return
        if self.connection in ("connected", "demo"):
            self.worker.submit("disconnect")
            return
        address = self.address.text().strip().upper()
        if not MAC.fullmatch(address):
            self.show_message("Choose paired earbuds or enter their Bluetooth address (AA:BB:CC:DD:EE:FF).", True)
            self.address.setFocus()
            return
        self.settings.setValue("address", address)
        self.settings.setValue("channel", self.channel.value())
        self.on_status("connecting", "Opening control connection…")
        self.worker.submit("connect", address, self.channel.value())

    def start_demo(self):
        self.worker.submit("demo")

    def on_status(self, state, detail):
        self.connection = state
        self.side_status.setText({"connected": "●  Connected", "demo": "◉  Demo mode", "connecting": "◌  Connecting…"}.get(state, "○  Disconnected"))
        self.status_text.setText(detail)
        self.connect_button.setText("Disconnect" if state in ("connected", "demo") else "Cancel" if state == "connecting" else "Connect")
        self.connect_button.setEnabled(True)
        for widget in (self.address, self.device_select, self.reload_button, self.demo_button):
            widget.setEnabled(state not in ("connecting", "connected", "demo"))
        if state == "demo":
            self.show_message("DEMO MODE · Simulated CMF Buds Pro 2. No Bluetooth commands are sent.", False)
        elif state == "connected":
            self.show_message("Connected locally over Bluetooth. Changes are checked against the device.", False)
        elif state == "disconnected":
            self.pending.clear()
            self.demo_button.setEnabled(True)
        self.render(self.state)

    def show_message(self, text, error=False):
        self.banner.setText(text)
        self.banner.setStyleSheet("background: #35221e; border-color: #81503e;" if error else "")

    def render(self, state):
        self.state = state
        known = state.get("model") in ("B172", "B187")
        ready = self.connection in ("connected", "demo") and known
        busy = bool(self.pending)
        self.refresh_button.setEnabled(self.connection in ("connected", "demo") and not busy)
        self.hero_status.setText("Demo device · explore every setting" if self.connection == "demo" else "Connected to your listening space." if ready else "Connect your earbuds to get started.")
        for name, tile in self.batteries.items():
            tile.update_value(state.get("battery", {}).get(name))
        anc = state.get("anc")
        for title, b in self.anc_buttons.items():
            b.setEnabled(ready and "anc" in state and not busy)
            b.setChecked(anc in ("High", "Mid", "Low", "Adaptive") if title == "Noise cancellation" else anc == title)
        self.anc_level.setEnabled(ready and anc in ("High", "Mid", "Low", "Adaptive") and not busy)
        if anc in ("High", "Mid", "Low", "Adaptive"):
            self.anc_level.setCurrentText(anc)
        for key, control in self.controls.items():
            available = ready and key in state and not busy
            control.setEnabled(available)
            control.setToolTip("Applying and checking setting…" if busy else "Reported by earbuds" if key in state else "Unavailable until the device reports this setting")
            control.blockSignals(True)
            if isinstance(control, QCheckBox):
                control.setChecked(bool(state.get(key, False)))
            elif key == "eq":
                text = state.get(key, "Waiting for device")
                if control.findText(text) < 0:
                    control.addItem(text)
                control.setCurrentText(text)
            elif key == "codec":
                control.setCurrentIndex(max(0, control.findData(state.get(key, -1))))
            control.blockSignals(False)
        bass = state.get("bass")
        self.bass_toggle.setEnabled(ready and bass is not None and not busy)
        self.bass_toggle.setChecked(bool(bass and bass[0]))
        self.bass_slider.setEnabled(ready and bool(bass and bass[0]) and not busy)
        if bass and not self.bass_slider.isSliderDown():
            self.bass_slider.setValue(round(bass[1] * 2))
        self.bass_value.setText(f"{bass[1]:g} / 5" if bass else "—")
        for b in self.find_buttons:
            b.setEnabled(ready and not busy)
        self.stop_button.setEnabled(ready)
        self.info.setText(f'Model {state.get("model", "—")}   ·   Firmware {state.get("firmware", "—")}')
        if self.connection == "connected" and state.get("model") and not known:
            self.show_message("This device is not a confirmed CMF Buds Pro 2. Settings are read-only to avoid sending commands for a different model.", True)

    def change(self, key, value):
        if self.pending:
            self.render(self.state)
            return
        self.pending.add(key)
        self.show_message("Applying setting and waiting for the earbuds to confirm…", False)
        self.render(self.state)
        self.worker.submit("write", key, value)

    def on_completed(self, key):
        self.pending.discard(key)
        self.render(self.state)

    def bass_changed(self):
        self.change("bass", (self.bass_toggle.isChecked(), self.bass_slider.value() / 2))

    def bass_keyboard(self, action):
        if not self.bass_slider.isSliderDown():
            QTimer.singleShot(0, self.bass_changed)

    def change_codec(self):
        value = self.codec_select.currentData()
        if value not in (0, 2):
            return
        result = QMessageBox.question(self, "Change audio codec?", "The earbuds may disconnect to change codecs. Reconnect here afterward to verify. LDAC may affect dual connection. Continue?")
        if result == QMessageBox.StandardButton.Yes:
            self.change("codec", value)
        else:
            self.render(self.state)

    def find_bud(self, side):
        result = QMessageBox.question(self, "Play locator sound?", "Take both earbuds out of your ears first. A locator tone will play for up to 15 seconds.")
        if result == QMessageBox.StandardButton.Yes:
            self.change("find", (side, True))
            QTimer.singleShot(15000, self.stop_ringing)

    def stop_ringing(self):
        if self.connection in ("connected", "demo"):
            self.worker.submit("write", "find", (2, False))
            self.worker.submit("write", "find", (3, False))

    def refresh(self):
        if self.connection in ("connected", "demo") and not self.pending:
            self.pending.add("_refresh")
            self.render(self.state)
            self.worker.submit("refresh")

    def restore(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit(self):
        self._closing = True
        self.close()

    def closeEvent(self, event):
        self.settings.setValue("tray", self.minimize_tray.isChecked())
        self.settings.setValue("channel", self.channel.value())
        if self.tray and self.minimize_tray.isChecked() and not self._closing:
            self.hide()
            event.ignore()
            return
        self.refresh_timer.stop()
        app = QApplication.instance()
        app.setQuitOnLastWindowClosed(False)
        self.worker.finished.connect(app.quit)
        self.worker.stop()
        if not self.worker.wait(250):

            self.hide()
            pass
        else:
            QTimer.singleShot(0, app.quit)
        if self.tray:
            self.tray.hide()
        event.accept()
