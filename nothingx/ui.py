from PySide6.QtCore import Qt, QSettings, QTimer, QRectF, QPointF, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QPushButton, QCheckBox, QComboBox, QSpinBox, QSlider, QHBoxLayout, QVBoxLayout,
    QScrollArea, QStackedWidget, QLineEdit, QMessageBox, QSystemTrayIcon,
    QMenu, QSizePolicy)

from .backend import Worker, MAC
from .audio import AudioWorker
from .core import NativeClient
from .protocol import ANC, EQ
from .artwork import COLORS, DEFAULT_COLOR, device_pixmap, device_thumbnail

from .themes import DEFAULT_THEME, THEMES, stylesheet, theme_data
from .components import DotLabel, BatteryRing, palette
from .preferences import read_preferences, save_preferences
from .models import MODELS, model_info
from .discovery import Discovery
from . import startup
from . import __version__
from .variants import variant_id
from .updater import Updater

STYLE = stylesheet()


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
        self.model = "B172"
        self.setMinimumSize(290, 175)
        self.setStyleSheet("background: transparent;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.set_color(color)

    def set_color(self, color):
        self.color = color
        self.images = {part: device_pixmap(color, part, self.model) for part in ("left", "right", "case", "headphone")}
        self.update()

    def set_model(self, model):
        if self.model != model:
            self.model = model
            self.set_color(self.color)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(self.width() / 420, self.height() / 200)
        p.translate((self.width() - 420 * scale) / 2, (self.height() - 200 * scale) / 2)
        p.scale(scale, scale)
        p.setPen(Qt.PenStyle.NoPen)
        for y in range(10, 200, 13):
            for x in range(8, 420, 13):
                p.setBrush(QColor(palette()["border"]))
                p.drawEllipse(QPointF(x, y), 0.8, 0.8)
        p.setOpacity(.18)
        p.setBrush(QColor(palette()["accent"]))
        p.drawEllipse(QRectF(260, 13, 145, 145))
        p.setOpacity(1)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if model_info(self.model)["kind"] in ("headphones", "neckband"):
            image = self.images["headphone"]
            p.drawPixmap(QRectF(118, 0, 185, 185), image, QRectF(image.rect()))
        else:
            for part, x in (("left", 20), ("right", 130)):
                source = QRectF(127, 44, 258, 424) if self.model in ("B172", "B187") else QRectF(self.images[part].rect())
                p.drawPixmap(QRectF(x, 24, 90, 148), self.images[part], source)
            source = QRectF(64, 64, 384, 384) if self.model in ("B172", "B187") else QRectF(self.images["case"].rect())
            p.drawPixmap(QRectF(250, 16, 165, 165), self.images["case"], source)
            p.setPen(QColor(palette()["muted"]))
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
        self.ring = BatteryRing()
        self.detail = label("Waiting for device", "muted")
        middle = QHBoxLayout()
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(58, 58)
        self.part = part
        self.set_color(color)
        middle.addWidget(self.thumbnail)
        middle.addStretch()
        middle.addWidget(self.ring)
        box.addLayout(middle)
        box.addWidget(self.detail)

    def set_color(self, color):
        self.color = color
        self.thumbnail.setPixmap(device_thumbnail(color, self.part, 58, getattr(self, "model", "B172")))

    def set_model(self, model):
        self.model = model
        self.set_color(self.color)

    def update_value(self, data):
        self.ring.set_value(data)
        self.detail.setText(("Last reported" if not data.get("available", True) else "Charging" if data["charging"] else "Battery level") if data else "Open case to update" if self.part == "case" else "Not reported")
        self.setToolTip("Keep a bud in the case with the lid open, then refresh. The closed case may not report its battery." if self.part == "case" else "")


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
        p.setBrush(QColor(palette()["accent"] if self.isChecked() else palette()["border"]))
        p.drawRoundedRect(QRectF(0, y, 38, 22), 11, 11)
        p.setBrush(QColor(palette()["ink"] if self.isChecked() else palette()["text"]))
        p.drawEllipse(QRectF(19 if self.isChecked() else 3, y + 3, 16, 16))
        p.setPen(QColor(palette()["text"]))
        p.drawText(QRectF(49, 0, max(0, self.width() - 49), self.height()), Qt.AlignmentFlag.AlignVCenter, self.text())
        if self.hasFocus():
            p.setPen(QPen(QColor(palette()["accent"]), 1, Qt.PenStyle.DotLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(0, y - 2, 40, 26), 12, 12)
        p.end()


class MainWindow(QMainWindow):
    def __init__(self, demo=False, auto_connect=False, demo_model="B172"):
        super().__init__()
        self.setWindowTitle("Nothing X")
        self.resize(1140, 850)
        self.setMinimumSize(920, 680)
        self.settings = QSettings("NothingXLinux", "NothingXLinux")
        self.theme_name = str(read_preferences().get("theme", self.settings.value("theme", DEFAULT_THEME)))
        self.apply_theme(self.theme_name)
        self.product_color = str(self.settings.value("product_color", DEFAULT_COLOR))
        if self.product_color not in COLORS.values():
            self.product_color = DEFAULT_COLOR
        self.state = {}
        self.pending = set()
        self.requested = {}
        self.connection = "disconnected"
        self.controls = {}
        self._closing = False
        self.auto_connect_requested = auto_connect
        self.backend_client = NativeClient(self, demo=demo)
        self.worker = Worker(self.backend_client, self)
        self.worker.state_changed.connect(self.render)
        self.worker.status.connect(self.on_status)
        self.worker.message.connect(self.show_message)
        self.worker.devices.connect(self.on_devices)
        self.worker.completed.connect(self.on_completed)
        self.audio = AudioWorker(self.backend_client, str(self.settings.value("address", "")), self)
        self.audio.message.connect(self.show_message)
        self.updater = Updater(self)
        self.updater.ready_to_restart.connect(self.quit)
        self._build()
        for number in range(4):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{number + 1}"), self)
            shortcut.activated.connect(lambda index=number: self.navigate(index))
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self.refresh)
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self.quit)
        self.demo_button.setVisible(demo)
        self._tray()
        self.worker.start()
        self.audio.start()
        if demo:
            self.worker.submit("demo", demo_model)
        else:
            self.worker.submit("devices")
        self.render({})
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(30000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()

    def apply_theme(self, name):
        self.theme_name = name if name in THEMES else DEFAULT_THEME
        self.settings.setValue("theme", self.theme_name)
        save_preferences(theme=self.theme_name)
        app = QApplication.instance()
        app.setProperty("nothingx_theme", self.theme_name)
        app.setStyleSheet(stylesheet(self.theme_name))
        if hasattr(self, "theme_select"):
            self.theme_select.setCurrentIndex(self.theme_select.findData(self.theme_name))
        for widget in self.findChildren(QWidget):
            widget.update()

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
        brand = DotLabel("NOTHING X", 3)
        side.addWidget(brand)
        side.addSpacing(38)
        self.pages = QStackedWidget()
        self.nav = []
        for index, text in enumerate(["◉   Overview", "≋   Sound", "♫   Audio", "⌘   Device"]):
            b = button(text, lambda checked=False, i=index: self.navigate(i))
            b.setObjectName("nav")
            b.setCheckable(True)
            b.setChecked(index == 0)
            self.nav.append(b)
            side.addWidget(b)
        side.addStretch()
        side.addWidget(label("THEME", "eyebrow"))
        self.theme_select = QComboBox()
        self.theme_select.setAccessibleName("Appearance theme")
        for key, item in THEMES.items():
            self.theme_select.addItem(item["name"], key)
        self.theme_select.setCurrentIndex(self.theme_select.findData(self.theme_name))
        self.theme_select.activated.connect(lambda: self.apply_theme(self.theme_select.currentData()))
        side.addWidget(self.theme_select)
        side.addSpacing(18)
        self.side_status = label("○  Disconnected", "muted", True)
        side.addWidget(self.side_status)
        side.addSpacing(13)
        self.demo_button = button("Demo mode", self.start_demo)
        side.addWidget(self.demo_button)
        base.addWidget(sidebar)
        main = QWidget()
        content = QVBoxLayout(main)
        content.setContentsMargins(30, 25, 30, 23)
        content.setSpacing(16)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        self.page_title = label("Overview", "title")
        heading.addWidget(self.page_title)
        header.addLayout(heading)
        header.addStretch()
        self.refresh_button = button("↻  Refresh", self.refresh)
        header.addWidget(self.refresh_button)
        content.addLayout(header)
        self.banner = label("Pair your audio device in your desktop’s Bluetooth settings, then connect below.", "banner", True)
        content.addWidget(self.banner)
        connection, row = card()
        row.setContentsMargins(15, 13, 15, 13)
        line = QHBoxLayout()
        self.device_select = QComboBox()
        self.device_select.addItem("Select paired device…", "")
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
        from .audio_ui import AudioPage
        self.audio_page = AudioPage(self.audio)
        audio_layout = self.page()
        audio_layout.addWidget(self.audio_page)
        self.device_page()
        footer = QHBoxLayout()
        self.status_text = label("Disconnected", "muted")
        footer.addWidget(self.status_text, 1)
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
        self.product_brand = label("CMF BY NOTHING", "eyebrow")
        text.addWidget(self.product_brand)
        name = label("Buds Pro 2")
        self.product_name = name
        name.setStyleSheet("font-size: 33px; font-weight: 650; background: transparent;")
        text.addWidget(name)
        self.hero_status = label("Disconnected", "muted", True)
        text.addWidget(self.hero_status)
        text.addStretch()
        appearance = QHBoxLayout()
        self.color_label = label("Colour", "muted")
        appearance.addWidget(self.color_label)
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
        for key, title, mark in [("left", "Left earbud", "L"), ("right", "Right earbud", "R"), ("case", "Charging case", "C"), ("headphone", "Headphones", "H")]:
            tile = BatteryTile(title, mark, key, self.product_color)
            self.batteries[key] = tile
            batteries.addWidget(tile)
        box.addLayout(batteries)
        noise, n = card("Noise control")
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
        self.anc_level.setMinimumWidth(140)
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
        eq_card, e = card("Equalizer")
        self.eq_select = QComboBox()
        self.eq_select.addItem("Waiting for device")
        self.eq_select.addItems(EQ)
        self.eq_select.activated.connect(lambda: self.change("eq", self.eq_select.currentText()))
        self.controls["eq"] = self.eq_select
        e.addWidget(self.eq_select)
        box.addWidget(eq_card)
        bass_card, b = card("Ultra Bass")
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
        extras, x = card("Audio settings")
        self.toggle_row(x, "spatial", "Spatial audio", "")
        self.toggle_row(x, "low_latency", "Low latency mode", "Reduce audio delay for games and video.")
        box.addWidget(extras)
        box.addStretch()

    def toggle_row(self, box, key, title, detail):
        row = QHBoxLayout()
        words = QVBoxLayout()
        words.addWidget(label(title))
        if detail:
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
        settings, s = card("Device settings")
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
        find, f = card("Find my device", "Remove the device from your ears before playing a locator sound.")
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
        box.addWidget(info)
        startup_card, startup_layout = card("Startup")
        self.startup_toggle = Switch("Open Nothing X at startup")
        self.startup_toggle.setChecked(startup.enabled())
        self.startup_toggle.clicked.connect(self.change_startup)
        startup_layout.addWidget(self.startup_toggle)
        box.addWidget(startup_card)
        update_card, update_layout = card("Updates", f"Version {__version__} · {variant_id()}")
        self.update_status = label("", "muted", True)
        update_layout.addWidget(self.update_status)
        update_actions = QHBoxLayout()
        self.check_update = button("Check for updates", self.updater.check)
        self.install_update = button("Install update and restart", self.confirm_update, True)
        self.install_update.setVisible(False)
        self.updater.status.connect(self.update_status.setText)
        self.updater.available.connect(self.install_update.setVisible)
        update_actions.addWidget(self.check_update)
        update_actions.addWidget(self.install_update)
        update_actions.addStretch()
        update_layout.addLayout(update_actions)
        box.addWidget(update_card)
        box.addStretch()

    def confirm_update(self):
        if QMessageBox.question(self, "Install update?", "Download the matching version from GitHub, verify it, then restart Nothing X?") == QMessageBox.StandardButton.Yes:
            self.updater.install()

    def change_startup(self, enabled):
        try:
            startup.set_enabled(enabled)
        except OSError as error:
            self.startup_toggle.setChecked(startup.enabled())
            self.show_message(f"Could not update startup settings: {error}", True)

    def _tray(self):
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(self)
            self.tray.setIcon(self.windowIcon() if not self.windowIcon().isNull() else QIcon.fromTheme("audio-headphones"))
            self.tray.setToolTip("Nothing X")
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
        self.page_title.setText(["Overview", "Sound", "Audio", "Device"][index])
        if index == 2:
            self.audio.submit()
        for i, b in enumerate(self.nav):
            b.setChecked(i == index)

    def on_devices(self, devices):
        current = self.address.text()
        self.device_select.blockSignals(True)
        self.device_select.clear()
        self.device_select.addItem("Select paired device…", "")
        for address, name in devices:
            self.device_select.addItem(name, address)
        self.device_select.blockSignals(False)
        if current:
            idx = self.device_select.findData(current)
            self.device_select.setCurrentIndex(max(0, idx))
        elif devices:
            matches = [(a, n) for a, n in devices if Discovery.matches(n)]
            if len(matches) == 1:
                self.device_select.setCurrentIndex(self.device_select.findData(matches[0][0]))
        if not devices:
            self.show_message("No paired devices found. Pair the buds in Bluetooth settings, then reload the list. You can also enter their address directly.", False)
        if self.auto_connect_requested and self.connection == "disconnected" and MAC.fullmatch(self.address.text()):
            self.auto_connect_requested = False
            self.connect_device()

    def select_device(self):
        address = self.device_select.currentData()
        if address:
            self.address.setText(address)
            self.audio.address = address.upper()
            self.audio.submit()

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
            self.show_message("Choose a paired device or enter their Bluetooth address (AA:BB:CC:DD:EE:FF).", True)
            self.address.setFocus()
            return
        self.settings.setValue("address", address)
        save_preferences(address=address)
        self.audio.address = address
        self.audio.submit()
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
            self.show_message("DEMO · Simulated audio device. No Bluetooth commands are sent.", False)
        elif state == "connected":
            self.banner.hide()
        elif state == "disconnected":
            self.pending.clear()
            self.requested.clear()
            self.demo_button.setEnabled(True)
        self.render(self.state)

    def show_message(self, text, error=False):
        self.banner.setText(text)
        self.banner.setStyleSheet(f"border-color: {palette()['accent']};" if error else "")
        self.banner.setVisible(error or self.connection not in ("connected", "demo") or text.startswith("DEMO"))
        self.status_text.setText(text)

    def render(self, state):
        self.state = state
        state = {**state, **self.requested}
        profile = model_info(state.get("model"))
        known = state.get("model") in MODELS
        caps = set(state.get("capabilities", profile.get("features", [])))
        if state.get("model") and getattr(self, "display_model", None) != state["model"]:
            self.display_model = state["model"]
            self.product_name.setText(profile["name"])
            self.product_brand.setText("CMF BY NOTHING" if profile["name"].startswith("CMF") else "NOTHING AUDIO")
            self.product_art.set_model(state["model"])
            for tile in self.batteries.values():
                tile.set_model(state["model"])
        single = profile["kind"] in ("headphones", "neckband")
        self.color_label.setVisible(profile.get("artwork") == "cmf-buds-pro-2")
        self.color_select.setVisible(profile.get("artwork") == "cmf-buds-pro-2")
        for part, tile in self.batteries.items():
            tile.setVisible((part == "headphone") if single else part != "headphone")
        choices = [preset["name"] for preset in profile.get("eq_presets", [])]
        if getattr(self, "eq_model", None) != state.get("model"):
            self.eq_model = state.get("model")
            self.eq_select.clear()
            self.eq_select.addItems(["Waiting for device", *choices])
        allowed_anc = profile.get("anc_modes", [])
        levels = [name for name in ("Adaptive", "High", "Mid", "Low") if name in allowed_anc]
        if [self.anc_level.itemText(i) for i in range(self.anc_level.count())] != levels:
            self.anc_level.clear()
            self.anc_level.addItems(levels)
        self.bass_slider.setMaximum(round(profile.get("bass_max", 5) * 2))
        ready = self.connection in ("connected", "demo") and known
        self.refresh_button.setEnabled(self.connection in ("connected", "demo") and "_refresh" not in self.pending)
        self.hero_status.setText("Demo mode" if self.connection == "demo" else "Connected" if ready else "Disconnected")
        for name, tile in self.batteries.items():
            tile.update_value(state.get("battery", {}).get(name))
        anc = state.get("anc")
        for title, b in self.anc_buttons.items():
            b.setEnabled(ready and "anc" in caps and "anc" in state and "anc" not in self.pending and (bool(levels) if title == "Noise cancellation" else title in allowed_anc))
            b.setChecked(anc in ("High", "Mid", "Low", "Adaptive") if title == "Noise cancellation" else anc == title)
        self.anc_level.setEnabled(ready and anc in ("High", "Mid", "Low", "Adaptive") and "anc" not in self.pending)
        if anc in ("High", "Mid", "Low", "Adaptive"):
            self.anc_level.setCurrentText(anc)
        for key, control in self.controls.items():
            busy = key in self.pending
            available = ready and key in caps and key in state and not busy
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
        self.bass_toggle.setEnabled(ready and "bass" in caps and bass is not None and "bass" not in self.pending)
        self.bass_toggle.setChecked(bool(bass and bass[0]))
        self.bass_slider.setEnabled(ready and "bass" in caps and bool(bass and bass[0]) and "bass" not in self.pending)
        if bass and not self.bass_slider.isSliderDown():
            self.bass_slider.setValue(round(bass[1] * 2))
        self.bass_value.setText(f"{bass[1]:g} / {profile.get('bass_max', 5)}" if bass else "—")
        for b in self.find_buttons:
            b.setEnabled(ready and "find" in caps and "find" not in self.pending)
        self.find_buttons[0].setText("Ring headphones" if single else "Ring device" if profile.get("ring_legacy") else "Ring left")
        self.find_buttons[1].setVisible(not single and not profile.get("ring_legacy"))
        self.stop_button.setEnabled(ready and "find" in caps)
        self.info.setText(f'Model {state.get("model", "—")}   ·   Firmware {state.get("firmware", "—")}')
        if self.connection == "connected" and state.get("model") and not known:
            self.show_message("This model is not in the device catalog. Battery and reported settings are available in read-only mode.", True)

    def change(self, key, value):
        if key == "anc" and value == "Adaptive" and value not in model_info(self.state.get("model")).get("anc_modes", []):
            value = self.anc_level.currentText()
        if key in self.pending:
            self.render(self.state)
            return
        self.pending.add(key)
        if key != "find":
            self.requested[key] = value
        self.show_message("Applying…", False)
        self.render(self.state)
        self.worker.submit("write", key, value)

    def on_completed(self, key):
        self.pending.discard(key)
        self.requested.pop(key, None)
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
        if model_info(self.state.get("model"))["kind"] in ("headphones", "neckband"):
            side = 6
        result = QMessageBox.question(self, "Play locator sound?", "Remove the device from your ears first. A locator tone will play for up to 15 seconds.")
        if result == QMessageBox.StandardButton.Yes:
            self.change("find", (side, True))
            QTimer.singleShot(15000, self.stop_ringing)

    def stop_ringing(self):
        if self.connection in ("connected", "demo"):
            profile = model_info(self.state.get("model"))
            sides = [2, 3]
            if profile["kind"] in ("headphones", "neckband"):
                sides = [6]
            elif profile.get("ring_legacy"):
                sides = [2]
            for side in sides:
                self.worker.submit("write", "find", (side, False))

    def refresh(self):
        self.audio.submit()
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
        self.updater.close()
        self.audio.stop()
        app = QApplication.instance()
        app.setQuitOnLastWindowClosed(False)
        def finish():
            if not self.worker.isRunning() and not self.audio.isRunning():
                app.quit()
        self.worker.finished.connect(finish)
        self.audio.finished.connect(finish)
        self.worker.stop()
        if self.worker.isRunning() or self.audio.isRunning():
            self.hide()
        else:
            QTimer.singleShot(0, app.quit)
        if self.tray:
            self.tray.hide()
        event.accept()
