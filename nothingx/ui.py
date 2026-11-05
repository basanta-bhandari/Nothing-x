from PySide6.QtCore import Qt, QSettings, QTimer, QRectF, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame, QLabel,
    QPushButton, QCheckBox, QComboBox, QSpinBox, QSlider, QHBoxLayout, QVBoxLayout,
    QScrollArea, QStackedWidget, QLineEdit, QMessageBox, QSystemTrayIcon, QMenu,
    QSizePolicy, QGridLayout, QTabWidget, QDialog, QDialogButtonBox, QListWidget,
    QListWidgetItem, QInputDialog, QProgressBar)

from .backend import Worker, MAC
from .audio import AudioWorker
from .core import NativeClient
from .artwork import COLORS, DEFAULT_COLOR, device_pixmap
from .themes import DEFAULT_THEME, THEMES, stylesheet, apply_palette
from .components import DotLabel, palette
from .preferences import read_preferences, save_preferences
from .models import MODELS, model_info
from .discovery import Discovery
from .widgets import ModeButton, Segments, Switch, ThemeSwatch, Slider
from . import startup, __version__
from .variants import variant_id
from .updater import Updater

STYLE = stylesheet()


def label(text, role=None, wrap=False):
    widget = QLabel(text)
    if role:
        widget.setObjectName(role)
    widget.setWordWrap(wrap)
    return widget


def button(text, callback=None, primary=False):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        widget.setObjectName("primary")
    if callback:
        widget.clicked.connect(callback)
    return widget


def card(title=None, subtitle=None):
    frame = QFrame()
    frame.setObjectName("card")
    box = QVBoxLayout(frame)
    box.setContentsMargins(22, 20, 22, 20)
    box.setSpacing(14)
    if title:
        box.addWidget(label(title, "section"))
    if subtitle:
        box.addWidget(label(subtitle, "muted", True))
    return frame, box


class BudsArt(QWidget):
    def __init__(self, color=DEFAULT_COLOR):
        super().__init__()
        self.model = "B172"
        self.color = color
        self.setMinimumSize(300, 200)
        self.setMaximumHeight(240)
        self.setObjectName("transparent")
        self.set_color(color)

    def set_color(self, color):
        self.color = color
        self.images = {part: device_pixmap(color, part, self.model) for part in ("left", "right", "case", "headphone")}
        self.update()

    def set_model(self, model):
        if model != self.model:
            self.model = model
            self.set_color(self.color)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        scale = min(self.width() / 420, self.height() / 220)
        p.translate((self.width() - 420 * scale) / 2, (self.height() - 220 * scale) / 2)
        p.scale(scale, scale)
        if model_info(self.model)["kind"] in ("headphones", "neckband"):
            image = self.images["headphone"]
            p.drawPixmap(QRectF(105, 5, 210, 210), image, QRectF(image.rect()))
        else:
            for part, x in (("left", 8), ("right", 126)):
                image = self.images[part]
                source = QRectF(127, 44, 258, 424) if self.model in ("B172", "B187") else QRectF(image.rect())
                p.drawPixmap(QRectF(x, 20, 100, 164), image, source)
            image = self.images["case"]
            source = QRectF(64, 64, 384, 384) if self.model in ("B172", "B187") else QRectF(image.rect())
            p.drawPixmap(QRectF(244, 14, 174, 174), image, source)


class BatteryTile(QFrame):
    def __init__(self, title, part):
        super().__init__()
        self.part = part
        self.setObjectName("transparent")
        self.setMaximumWidth(155)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 10, 0)
        box.setSpacing(6)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(4)
        self.value = label(title + "  —")
        self.detail = label("", "muted")
        box.addWidget(self.bar)
        box.addWidget(self.value)
        box.addWidget(self.detail)
        self.title = title

    def update_value(self, data):
        level = data.get("level") if data else None
        self.bar.setValue(level or 0)
        self.value.setText(f"{self.title}  {level}%" if level is not None else self.title + "  —")
        stale = data is not None and not data.get("available", True)
        self.detail.setText("Last reported" if stale else "Charging" if data and data.get("charging") else "")
        self.setToolTip("Last case reading. Open the case with a bud inside to refresh." if self.part == "case" else "")


class MainWindow(QMainWindow):
    def __init__(self, demo=False, auto_connect=False, demo_model="B172"):
        super().__init__()
        self.setWindowTitle("Nothing X")
        self.resize(1120, 850)
        self.setMinimumSize(880, 700)
        self.settings = QSettings("NothingXLinux", "NothingXLinux")
        preferences = read_preferences()
        self.theme_name = str(preferences.get("theme", DEFAULT_THEME))
        self.product_color = str(preferences.get("product_color", self.settings.value("product_color", DEFAULT_COLOR)))
        if self.product_color not in COLORS.values():
            self.product_color = DEFAULT_COLOR
        self.state = {}
        self.pending = set()
        self.requested = {}
        self.connection = "disconnected"
        self.controls = {}
        self.control_rows = {}
        self.feature_cards = {}
        self._closing = False
        self.demo = demo
        self.shared = False
        self.explicit_connect = auto_connect
        self.devices = []
        self.picker = None
        self.preset_queue = []
        self.preset_active = None
        self.user_disconnected = False
        self.display_model = demo_model if demo else preferences.get("device_state", {}).get(preferences.get("address", ""), {}).get("model", "B172")
        self.auto_connect_requested = auto_connect or (bool(preferences.get("address")) and preferences.get("auto_reconnect", True))
        self.backend_client = NativeClient(self, demo=demo)
        self.backend_client.event.connect(self.meta_event)
        self.worker = Worker(self.backend_client, self)
        self.worker.state_changed.connect(self.render)
        self.worker.status.connect(self.on_status)
        self.worker.message.connect(self.show_message)
        self.worker.devices.connect(self.on_devices)
        self.worker.completed.connect(self.on_completed)
        self.audio = AudioWorker(self.backend_client, preferences.get("address", ""), self)
        self.audio.message.connect(self.show_message)
        self.updater = Updater(self)
        self.updater.ready_to_restart.connect(self.quit)
        self.apply_theme(self.theme_name, persist=False)
        self._build()
        self._tray()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(30000)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()
        self.theme_timer = QTimer(self)
        self.theme_timer.setInterval(1000)
        self.theme_timer.timeout.connect(self.sync_theme)
        self.theme_timer.start()
        self.bass_timer = QTimer(self)
        self.bass_timer.setSingleShot(True)
        self.bass_timer.setInterval(180)
        self.bass_timer.timeout.connect(self.bass_changed)
        for index in range(3):
            QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self).activated.connect(lambda i=index: self.navigate(i))
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self.refresh)
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self.quit)
        self.worker.start()
        self.audio.start()
        self.worker.submit("demo", demo_model) if demo else self.worker.submit("devices")
        self.render({})

    def apply_theme(self, name, persist=True):
        self.theme_name = name if name in THEMES else DEFAULT_THEME
        apply_palette(QApplication.instance(), self.theme_name)
        if persist:
            save_preferences(theme=self.theme_name)
            self.settings.setValue("theme", self.theme_name)
            if hasattr(self, "worker"):
                self.backend_client.send({"action": "preferences"})
        for key, control in getattr(self, "theme_buttons", {}).items():
            control.setChecked(key == self.theme_name)
        if hasattr(self, "theme_shortcut"):
            self.theme_shortcut.setText("Theme · " + THEMES[self.theme_name]["name"])
        for widget in self.findChildren(QWidget):
            widget.update()

    def sync_theme(self):
        name = read_preferences().get("theme", DEFAULT_THEME)
        if name != self.theme_name:
            self.apply_theme(name, persist=False)

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        base = QHBoxLayout(root)
        base.setContentsMargins(0, 0, 0, 0)
        base.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(172)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 28, 16, 24)
        side.addWidget(DotLabel("NOTHING X", 2))
        side.addSpacing(40)
        self.nav = []
        for index, title in enumerate(("Device", "Audio", "Settings")):
            control = button(title, lambda checked=False, i=index: self.navigate(i))
            control.setObjectName("nav")
            control.setCheckable(True)
            side.addWidget(control)
            self.nav.append(control)
        side.addStretch()
        self.side_status = label("Disconnected", "muted", True)
        side.addWidget(self.side_status)
        self.appearance_link = button("Themes", lambda: self.open_settings(1))
        side.addWidget(self.appearance_link)
        side.addWidget(label("Nothing X  ·  " + __version__, "muted"))
        base.addWidget(sidebar)
        column = QVBoxLayout()
        column.setContentsMargins(28, 24, 28, 16)
        container = QWidget()
        container.setMaximumWidth(1050)
        content = QVBoxLayout(container)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(16)
        heading = QHBoxLayout()
        self.page_title = label("My device", "title")
        heading.addWidget(self.page_title, 1)
        self.hero_status = label("Disconnected", "status")
        heading.addWidget(self.hero_status)
        self.theme_shortcut = button("Theme · " + THEMES[self.theme_name]["name"], lambda: self.open_settings(1))
        heading.addWidget(self.theme_shortcut)
        self.connect_button = button("Connect", self.connect_device)
        heading.addWidget(self.connect_button)
        more = button("•••")
        more.setAccessibleName("Device actions")
        menu = QMenu(more)
        menu.addAction("Choose device", self.choose_device)
        menu.addAction("Refresh", self.refresh)
        self.disconnect_action = menu.addAction("Disconnect", self.disconnect_device)
        more.setMenu(menu)
        heading.addWidget(more)
        content.addLayout(heading)
        self.banner = label("", "banner", True)
        self.banner.hide()
        content.addWidget(self.banner)
        self.pages = QStackedWidget()
        content.addWidget(self.pages, 1)
        self.status_text = label("", "muted")
        content.addWidget(self.status_text)
        column.addWidget(container, 1, Qt.AlignmentFlag.AlignHCenter)
        base.addLayout(column, 1)
        self.address = QLineEdit(str(read_preferences().get("address", self.settings.value("address", ""))))
        self.address.setPlaceholderText("AA:BB:CC:DD:EE:FF")
        self.address.setAccessibleName("Bluetooth address")
        self.device_select = QComboBox()
        self.device_select.currentIndexChanged.connect(self.select_device)
        self.overview()
        from .audio_ui import AudioPage
        self.audio_page = AudioPage(self.audio)
        audio = self.page()
        audio.addWidget(self.audio_page)
        self.device_page()
        self.navigate(0)

    def page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("pageBody")
        box = QVBoxLayout(body)
        box.setContentsMargins(0, 0, 6, 0)
        box.setSpacing(14)
        scroll.setWidget(body)
        self.pages.addWidget(scroll)
        return box

    def overview(self):
        box = self.page()
        hero = QWidget()
        hero.setObjectName("transparent")
        hero.setMinimumHeight(215)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        self.product_art = BudsArt(self.product_color)
        hero_layout.addWidget(self.product_art, 1)
        words = QVBoxLayout()
        words.setSpacing(12)
        words.addStretch()
        self.product_brand = label("CMF BY NOTHING", "eyebrow")
        words.addWidget(self.product_brand)
        self.product_name = label("CMF Buds Pro 2", "product", True)
        words.addWidget(self.product_name)
        battery_row = QHBoxLayout()
        self.batteries = {}
        for key, title in (("left", "L"), ("right", "R"), ("case", "Case"), ("headphone", "Battery")):
            tile = BatteryTile(title, key)
            self.batteries[key] = tile
            battery_row.addWidget(tile, 1)
        words.addLayout(battery_row)
        words.addStretch()
        hero_layout.addLayout(words, 1)
        box.addWidget(hero)
        mode_row = QHBoxLayout()
        noise, n = card("Noise cancellation")
        self.anc_summary = label("Connect to view noise control", "muted")
        n.addWidget(self.anc_summary)
        choices = QHBoxLayout()
        self.anc_buttons = {}
        for title, value, icon in (("Cancellation", "Noise cancellation", "anc"), ("Transparency", "Transparency", "transparency"), ("Off", "Off", "off")):
            control = ModeButton(title, icon)
            control.clicked.connect(lambda checked=False, name=value: self.noise_changed(name))
            choices.addWidget(control, 1)
            self.anc_buttons[value] = control
        n.addLayout(choices)
        self.anc_strength = Segments(("Low", "Mid", "High", "Adaptive"))
        self.anc_strength.selected.connect(lambda value: self.change("anc", value))
        n.addWidget(self.anc_strength)
        mode_row.addWidget(noise, 2)
        self.feature_cards["anc"] = noise
        spatial, s = card("Spatial audio")
        s.addWidget(label("A wider soundstage", "muted"))
        spatial_options = QHBoxLayout()
        self.spatial_on = ModeButton("Fixed", "spatial")
        self.spatial_off = ModeButton("Off", "off")
        self.spatial_on.clicked.connect(lambda checked=False: self.change("spatial", True))
        self.spatial_off.clicked.connect(lambda checked=False: self.change("spatial", False))
        spatial_options.addWidget(self.spatial_on)
        spatial_options.addWidget(self.spatial_off)
        s.addLayout(spatial_options)
        s.addStretch()
        mode_row.addWidget(spatial, 1)
        self.feature_cards["spatial"] = spatial
        box.addLayout(mode_row)
        sound_row = QHBoxLayout()
        eq, e = card("Equalizer")
        self.eq_select = QComboBox()
        self.eq_select.setAccessibleName("Equalizer preset")
        self.eq_select.activated.connect(lambda index: self.change("eq", self.eq_select.itemText(index)))
        self.controls["eq"] = self.eq_select
        e.addWidget(self.eq_select)
        e.addStretch()
        sound_row.addWidget(eq, 1)
        self.feature_cards["eq"] = eq
        bass, b = card("Ultra Bass")
        top = QHBoxLayout()
        self.bass_toggle = Switch()
        self.bass_toggle.setAccessibleName("Ultra Bass")
        self.bass_toggle.clicked.connect(self.bass_changed)
        self.bass_value = label("—", "muted")
        top.addWidget(self.bass_toggle)
        top.addStretch()
        top.addWidget(self.bass_value)
        b.addLayout(top)
        self.bass_slider = Slider(Qt.Orientation.Horizontal)
        self.bass_slider.setRange(0, 10)
        self.bass_slider.setTickInterval(2)
        self.bass_slider.setSingleStep(1)
        self.bass_slider.setPageStep(2)
        self.bass_slider.setMinimumHeight(30)
        self.bass_slider.setAccessibleName("Ultra Bass level")
        self.bass_slider.valueChanged.connect(lambda value: self.bass_value.setText(f"Level {value / 2:g}"))
        self.bass_slider.sliderReleased.connect(self.bass_changed)
        self.bass_slider.actionTriggered.connect(lambda _: self.bass_timer.start() if not self.bass_slider.isSliderDown() else None)
        b.addWidget(self.bass_slider)
        sound_row.addWidget(bass, 1)
        self.feature_cards["bass"] = bass
        everyday, d = card("Playback")
        self.toggle_row(d, "low_latency", "Low lag mode", "")
        self.toggle_row(d, "dual", "Dual connection", "")
        sound_row.addWidget(everyday, 1)
        self.playback_card = everyday
        box.addLayout(sound_row)
        presets, p = card("Your sound presets")
        preset_row = QHBoxLayout()
        self.preset_select = QComboBox()
        self.preset_select.setAccessibleName("Saved sound preset")
        self.preset_select.activated.connect(self.apply_preset)
        preset_row.addWidget(self.preset_select, 1)
        self.save_preset = button("Save current", self.save_sound_preset)
        preset_row.addWidget(self.save_preset)
        self.delete_preset = button("Delete", self.delete_sound_preset)
        self.delete_preset.hide()
        self.preset_select.currentIndexChanged.connect(lambda index: self.delete_preset.setVisible(index > 0))
        preset_row.addWidget(self.delete_preset)
        p.addLayout(preset_row)
        box.addWidget(presets)
        box.addStretch()

    def toggle_row(self, layout, key, title, detail):
        container = QWidget()
        container.setObjectName("transparent")
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        words = QVBoxLayout()
        words.addWidget(label(title))
        if detail:
            words.addWidget(label(detail, "muted", True))
        row.addLayout(words, 1)
        control = Switch()
        control.setAccessibleName(title)
        control.clicked.connect(lambda value, name=key: self.change(name, value))
        row.addWidget(control)
        layout.addWidget(container)
        self.controls[key] = control
        self.control_rows[key] = container

    def device_page(self):
        box = self.page()
        self.settings_tabs = QTabWidget()
        self.settings_tabs.currentChanged.connect(self.resize_settings)
        box.addWidget(self.settings_tabs)
        device = QWidget()
        d = QVBoxLayout(device)
        d.setContentsMargins(0, 0, 0, 0)
        d.setSpacing(14)
        self.settings_tabs.addTab(device, "Device")
        settings, s = card("Device preferences")
        self.toggle_row(s, "in_ear", "In-ear detection", "Pause when you remove an earbud.")
        self.codec_row = QWidget()
        self.codec_row.setObjectName("transparent")
        codec_row = QHBoxLayout(self.codec_row)
        codec_row.setContentsMargins(0, 0, 0, 0)
        codec_row.addWidget(label("High-quality audio"), 1)
        self.codec_select = QComboBox()
        self.codec_select.addItem("Standard · AAC / SBC", 0)
        self.codec_select.addItem("LDAC", 2)
        self.codec_select.activated.connect(self.change_codec)
        self.controls["codec"] = self.codec_select
        codec_row.addWidget(self.codec_select)
        s.addWidget(self.codec_row)
        self.device_preferences_card = settings
        d.addWidget(settings)
        name_card, names = card("Device name", "A name for this desktop.")
        row = QHBoxLayout()
        self.alias_input = QLineEdit()
        self.alias_input.setMaxLength(40)
        row.addWidget(self.alias_input, 1)
        row.addWidget(button("Save", self.save_alias))
        names.addLayout(row)
        d.addWidget(name_card)
        find, f = card("Find my device", "Remove it from your ears before playing a sound.")
        row = QHBoxLayout()
        self.find_buttons = []
        for title, side in (("Ring left", 2), ("Ring right", 3)):
            control = button(title, lambda checked=False, target=side: self.find_bud(target))
            row.addWidget(control)
            self.find_buttons.append(control)
        self.stop_button = button("Stop", self.stop_ringing)
        row.addWidget(self.stop_button)
        f.addLayout(row)
        d.addWidget(find)
        self.find_card = find
        advanced, a = card()
        disclosure = button("Connection details")
        disclosure.setCheckable(True)
        a.addWidget(disclosure)
        detail = QWidget()
        detail.setObjectName("transparent")
        detail_box = QVBoxLayout(detail)
        detail_box.setContentsMargins(0, 0, 0, 0)
        self.info = label("Model —  ·  Firmware —", "muted", True)
        self.info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail_box.addWidget(self.info)
        detail_box.addWidget(self.address)
        row = QHBoxLayout()
        row.addWidget(label("Control channel", "muted"))
        self.channel = QSpinBox()
        self.channel.setRange(0, 30)
        self.channel.setSpecialValueText("Automatic")
        self.channel.setValue(int(self.settings.value("channel", 0)))
        row.addWidget(self.channel)
        row.addStretch()
        detail_box.addLayout(row)
        a.addWidget(detail)
        detail.hide()
        disclosure.toggled.connect(detail.setVisible)
        d.addWidget(advanced)
        d.addStretch()
        appearance = QWidget()
        ap = QVBoxLayout(appearance)
        ap.setContentsMargins(0, 0, 0, 0)
        theme_card, theme_box = card("Appearance", "Applied to the app and panel.")
        swatches = QGridLayout()
        swatches.setSpacing(12)
        self.theme_buttons = {}
        for index, (key, theme) in enumerate(THEMES.items()):
            swatch = ThemeSwatch(theme)
            swatch.setChecked(key == self.theme_name)
            swatch.clicked.connect(lambda checked=False, name=key: self.apply_theme(name))
            swatches.addWidget(swatch, index // 3, index % 3)
            self.theme_buttons[key] = swatch
        theme_box.addLayout(swatches)
        ap.addWidget(theme_card)
        color, c = card("Product colour")
        self.color_select = QComboBox()
        for name, value in COLORS.items():
            self.color_select.addItem(name, value)
        self.color_select.setCurrentIndex(self.color_select.findData(self.product_color))
        self.color_select.activated.connect(self.change_color)
        c.addWidget(self.color_select)
        self.color_card = color
        ap.addWidget(color)
        ap.addStretch()
        self.settings_tabs.addTab(appearance, "Themes")
        app_page = QWidget()
        app_box = QVBoxLayout(app_page)
        app_box.setContentsMargins(0, 0, 0, 0)
        preferences, p = card("App preferences")
        self.startup_toggle = Switch("Open at startup")
        self.startup_toggle.setChecked(startup.enabled())
        self.startup_toggle.clicked.connect(self.change_startup)
        p.addWidget(self.startup_toggle)
        self.reconnect_toggle = Switch("Reconnect automatically")
        self.reconnect_toggle.setChecked(read_preferences().get("auto_reconnect", True))
        self.reconnect_toggle.clicked.connect(lambda value: save_preferences(auto_reconnect=value))
        p.addWidget(self.reconnect_toggle)
        self.minimize_tray = Switch("Keep running when the window closes")
        self.minimize_tray.setChecked(self.settings.value("tray", False, type=bool))
        self.minimize_tray.setVisible(not variant_id().endswith("applet"))
        p.addWidget(self.minimize_tray)
        if variant_id().endswith("applet"):
            p.addWidget(label("The panel remains available when this window closes.", "muted", True))
        app_box.addWidget(preferences)
        updates, u = card("Updates", f"Version {__version__} · {variant_id()}")
        self.update_status = label("", "muted", True)
        u.addWidget(self.update_status)
        actions = QHBoxLayout()
        actions.addWidget(button("Check for updates", self.updater.check))
        self.install_update = button("Install and restart", self.confirm_update, True)
        self.install_update.hide()
        self.updater.status.connect(self.update_status.setText)
        self.updater.available.connect(self.install_update.setVisible)
        actions.addWidget(self.install_update)
        actions.addStretch()
        u.addLayout(actions)
        app_box.addWidget(updates)
        app_box.addStretch()
        self.settings_tabs.addTab(app_page, "App")
        box.addStretch()

    def resize_settings(self, index):
        for number in range(self.settings_tabs.count()):
            self.settings_tabs.widget(number).setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred if number == index else QSizePolicy.Policy.Ignored)
        self.settings_tabs.updateGeometry()

    def _tray(self):
        self.tray = None
        self.tray_modes = {}
        if variant_id().endswith("applet") or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setIcon(QApplication.windowIcon())
        menu = QMenu(self)
        menu.addAction("Open Nothing X", self.restore)
        noise = menu.addMenu("Noise control")
        for title in ("Noise cancellation", "Transparency", "Off"):
            action = noise.addAction(title)
            action.setCheckable(True)
            action.triggered.connect(lambda checked=False, name=title: self.noise_changed(name))
            self.tray_modes[title] = action
        self.tray_mute = menu.addAction("Mute audio")
        self.tray_mute.setCheckable(True)
        self.tray_mute.triggered.connect(lambda value: self.audio.submit("output_mute", value))
        self.audio.state_changed.connect(lambda state: self.tray_mute.setChecked(bool((state.get("sink") or {}).get("mute"))))
        menu.addSeparator()
        menu.addAction("Quit", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.restore() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        self.page_title.setText(("My device", "Audio", "Settings")[index])
        for number, control in enumerate(self.nav):
            control.setChecked(index == number)
        if index == 1:
            self.audio.submit()

    def open_settings(self, index=0):
        self.navigate(2)
        self.settings_tabs.setCurrentIndex(index)

    def meta_event(self, event):
        if event.get("type") == "ready":
            self.shared = bool(event.get("shared"))
            if self.shared and not self.explicit_connect:
                self.auto_connect_requested = False
        address = event.get("address")
        if address and hasattr(self, "address"):
            self.address.setText(address)

    def choose_device(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Choose device")
        dialog.resize(440, 390)
        box = QVBoxLayout(dialog)
        box.setSpacing(14)
        box.addWidget(label("Your devices", "title"))
        box.addWidget(label("Pair a new device in your system Bluetooth settings.", "muted", True))
        devices = QListWidget()
        self.picker = devices
        self.populate_picker()
        box.addWidget(devices, 1)
        if not devices.count():
            box.addWidget(label("No paired Nothing devices found.", "muted"))
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        actions.button(QDialogButtonBox.StandardButton.Ok).setText("Connect")
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        devices.itemDoubleClicked.connect(lambda _: dialog.accept())
        box.addWidget(actions)
        self.worker.submit("devices")
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        selected = devices.currentItem().data(Qt.ItemDataRole.UserRole) if devices.currentItem() else None
        self.picker = None
        if accepted and selected:
            self.address.setText(selected)
            self.connect_device(force=True)

    def populate_picker(self):
        if self.picker is None:
            return
        selected = self.picker.currentItem().data(Qt.ItemDataRole.UserRole) if self.picker.currentItem() else self.address.text().upper()
        self.picker.clear()
        for address, name in self.devices:
            if Discovery.matches(name) or address.upper() == self.address.text().upper():
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, address)
                item.setToolTip(address)
                self.picker.addItem(item)
                if address.upper() == selected.upper():
                    self.picker.setCurrentItem(item)

    def on_devices(self, devices):
        self.devices = devices
        self.populate_picker()
        current = self.address.text().upper()
        self.device_select.blockSignals(True)
        self.device_select.clear()
        for address, name in devices:
            self.device_select.addItem(name, address)
        self.device_select.blockSignals(False)
        if current:
            self.device_select.setCurrentIndex(self.device_select.findData(current))
        else:
            matches = [(address, name) for address, name in devices if Discovery.matches(name)]
            if len(matches) == 1:
                self.address.setText(matches[0][0])
        if self.auto_connect_requested and self.connection == "disconnected" and MAC.fullmatch(self.address.text()):
            self.auto_connect_requested = False
            self.connect_device()

    def select_device(self):
        address = self.device_select.currentData()
        if address and self.connection == "disconnected":
            self.address.setText(address)

    def connect_device(self, checked=False, force=False):
        if self.connection == "connecting" and not force:
            self.disconnect_device()
            return
        if self.connection in ("connected", "demo") and not force:
            return
        address = self.address.text().strip().upper()
        if not MAC.fullmatch(address):
            self.choose_device()
            return
        self.user_disconnected = False
        self.auto_connect_requested = False
        self.settings.setValue("address", address)
        save_preferences(address=address)
        self.preset_queue.clear()
        self.worker.submit("connect", address, self.channel.value())

    def disconnect_device(self):
        self.user_disconnected = True
        self.preset_queue.clear()
        self.worker.submit("disconnect")

    def on_status(self, phase, detail):
        self.connection = phase
        title = {"connected": "Connected", "connecting": "Connecting…", "demo": "Demo"}.get(phase, "Disconnected")
        self.side_status.setText(title)
        self.hero_status.setText(title)
        self.connect_button.setText("Cancel" if phase == "connecting" else "Connect")
        self.connect_button.setVisible(phase not in ("connected", "demo"))
        self.disconnect_action.setEnabled(phase in ("connected", "connecting"))
        if phase in ("connected", "demo"):
            self.banner.hide()
        elif phase == "disconnected":
            self.pending.clear()
            self.requested.clear()
            self.preset_queue.clear()
            self.banner.setText("Put both buds in the case and open the case before pressing Connect. It makes life easier.")
            self.banner.show()
        self.render(self.state)

    def show_message(self, text, error=False):
        if error:
            self.banner.setText(text)
            self.banner.show()
        else:
            self.status_text.setText("Saved" if text == "Updated" else text)
            QTimer.singleShot(4000, lambda: self.status_text.setText(""))

    def render(self, state):
        self.state = state
        shown = {**state, **self.requested}
        model = shown.get("model", self.display_model)
        profile = model_info(model)
        caps = set(profile.get("features", []))
        known = model in MODELS
        ready = self.connection in ("connected", "demo") and known
        if model != self.display_model or not getattr(self, "model_loaded", False) or getattr(self, "display_address", "") != self.address.text().upper():
            self.model_loaded = True
            self.display_address = self.address.text().upper()
            self.display_model = model
            self.product_art.set_model(model)
            self.product_brand.setText("CMF BY NOTHING" if profile["name"].startswith("CMF") else "NOTHING AUDIO")
            names = read_preferences().get("device_names", {})
            self.product_name.setText(names.get(self.address.text().upper(), profile["name"]))
            self.alias_input.setPlaceholderText(profile["name"])
            self.alias_input.setText(names.get(self.address.text().upper(), ""))
            self.eq_select.blockSignals(True)
            self.eq_select.clear()
            self.eq_select.addItems([item["name"] for item in profile.get("eq_presets", [])])
            self.eq_select.blockSignals(False)
            self.load_presets()
        single = profile["kind"] in ("headphones", "neckband")
        for part, tile in self.batteries.items():
            tile.setVisible(part == "headphone" if single else part != "headphone")
            tile.update_value(shown.get("battery", {}).get(part))
        self.color_card.setVisible(profile.get("artwork") == "cmf-buds-pro-2")
        for feature, frame in self.feature_cards.items():
            frame.setVisible(feature in caps)
        anc = shown.get("anc")
        cancelled = anc in ("Low", "Mid", "High", "Adaptive")
        self.anc_summary.setText("On · " + anc if cancelled else anc or "Connect to view noise control")
        for title, control in self.anc_buttons.items():
            control.setChecked(cancelled if title == "Noise cancellation" else anc == title)
            control.setEnabled(ready and "anc" in state and "anc" not in self.pending and (title == "Noise cancellation" or title in profile.get("anc_modes", [])))
        levels = [value for value in ("Low", "Mid", "High", "Adaptive") if value in profile.get("anc_modes", [])]
        self.anc_strength.set_values(levels)
        self.anc_strength.set_value(anc)
        self.anc_strength.setEnabled(ready and cancelled and "anc" not in self.pending)
        self.spatial_on.setChecked(bool(shown.get("spatial")))
        self.spatial_off.setChecked("spatial" in shown and not shown["spatial"])
        self.spatial_on.setEnabled(ready and "spatial" in state and "spatial" not in self.pending)
        self.spatial_off.setEnabled(self.spatial_on.isEnabled())
        self.playback_card.setVisible(bool(caps.intersection({"low_latency", "dual"})))
        self.device_preferences_card.setVisible(bool(caps.intersection({"in_ear", "codec"})))
        self.codec_row.setVisible("codec" in caps)
        self.find_card.setVisible("find" in caps)
        for key, control in self.controls.items():
            if key in self.control_rows:
                self.control_rows[key].setVisible(key in caps)
            control.setVisible(key in caps)
            control.setEnabled(ready and key in state and key not in self.pending)
            control.setToolTip("Saving…" if key in self.pending else "")
            control.blockSignals(True)
            if isinstance(control, QCheckBox):
                control.setChecked(bool(shown.get(key)))
            elif key == "eq":
                control.setCurrentText(shown.get(key, ""))
            elif key == "codec":
                control.setCurrentIndex(max(0, control.findData(shown.get(key, 0))))
            control.blockSignals(False)
        bass = shown.get("bass")
        self.bass_toggle.blockSignals(True)
        self.bass_toggle.setChecked(bool(bass and bass[0]))
        self.bass_toggle.blockSignals(False)
        self.bass_toggle.setEnabled(ready and "bass" in state and "bass" not in self.pending)
        self.bass_slider.setEnabled(self.bass_toggle.isEnabled() and bool(bass and bass[0]))
        self.bass_slider.blockSignals(True)
        self.bass_slider.setMaximum(round(profile.get("bass_max", 5) * 2))
        if bass and not self.bass_slider.isSliderDown():
            self.bass_slider.setValue(round(bass[1] * 2))
        self.bass_slider.blockSignals(False)
        self.bass_value.setText(f"Level {bass[1]:g}" if bass else "Off")
        for control in self.find_buttons:
            control.setEnabled(ready and "find" in caps and "find" not in self.pending)
        self.find_buttons[0].setText("Ring device" if single or profile.get("ring_legacy") else "Ring left")
        self.find_buttons[1].setVisible(not single and not profile.get("ring_legacy"))
        self.stop_button.setEnabled(ready and "find" in caps)
        self.info.setText(f'Model {model}  ·  Firmware {state.get("firmware", "—")}')
        self.save_preset.setEnabled(ready)
        self.preset_select.setEnabled(ready and self.preset_select.count() > 1 and not self.preset_queue and self.preset_active is None)
        for title, action in self.tray_modes.items():
            action.setEnabled(ready and "anc" in state)
            action.setChecked(cancelled if title == "Noise cancellation" else title == anc)
        if self.tray:
            self.tray.setToolTip(self.product_name.text() + " · " + self.hero_status.text())

    def noise_changed(self, value):
        if value == "Noise cancellation":
            levels = model_info(self.display_model).get("anc_modes", [])
            value = next((v for v in (self.state.get("anc"), "Adaptive", "High", "Low") if v in levels and v not in ("Off", "Transparency")), "High")
        self.change("anc", value)

    def change(self, key, value, preset=False):
        if self.connection not in ("connected", "demo") or key in self.pending:
            return
        if not preset:
            self.preset_queue.clear()
            self.preset_active = None
        self.pending.add(key)
        if key != "find":
            self.requested[key] = value
        self.render(self.state)
        self.worker.submit("write", key, value)

    def on_completed(self, key):
        self.pending.discard(key)
        self.requested.pop(key, None)
        if self.preset_active and self.preset_active[0] == key:
            expected = self.preset_active[1]
            actual = self.state.get(key)
            if isinstance(actual, tuple):
                actual = list(actual)
            if actual != expected:
                self.preset_queue.clear()
                self.show_message("Preset stopped because the device did not confirm a setting.", True)
            self.preset_active = None
            QTimer.singleShot(0, self.next_preset_setting)
        self.render(self.state)

    def bass_changed(self, *_):
        self.bass_timer.stop()
        self.change("bass", [self.bass_toggle.isChecked(), self.bass_slider.value() / 2])

    def load_presets(self):
        self.preset_select.clear()
        self.preset_select.addItem("Choose a saved preset", None)
        for preset in read_preferences().get("sound_presets", {}).get(self.display_model, []):
            self.preset_select.addItem(preset["name"], preset["settings"])

    def save_sound_preset(self):
        name, accepted = QInputDialog.getText(self, "Save sound preset", "Preset name")
        if not accepted or not name.strip():
            return
        values = {key: list(value) if isinstance(value, tuple) else value for key, value in self.state.items() if key in ("anc", "eq", "bass", "spatial", "low_latency")}
        presets = read_preferences().get("sound_presets", {})
        items = [item for item in presets.get(self.display_model, []) if item["name"] != name.strip()]
        presets[self.display_model] = [*items, {"name": name.strip()[:40], "settings": values}]
        save_preferences(sound_presets=presets)
        self.load_presets()
        self.show_message("Preset saved")

    def delete_sound_preset(self):
        name = self.preset_select.currentText()
        if self.preset_select.currentData() is None:
            return
        presets = read_preferences().get("sound_presets", {})
        presets[self.display_model] = [item for item in presets.get(self.display_model, []) if item["name"] != name]
        save_preferences(sound_presets=presets)
        self.load_presets()

    def apply_preset(self, index):
        values = self.preset_select.itemData(index)
        if not values:
            return
        self.preset_queue = [(key, value) for key, value in values.items() if key in self.state and key not in self.pending]
        self.next_preset_setting()

    def next_preset_setting(self):
        if self.preset_queue:
            self.preset_active = self.preset_queue.pop(0)
            self.change(*self.preset_active, preset=True)
        else:
            self.render(self.state)

    def save_alias(self):
        names = read_preferences().get("device_names", {})
        key = self.address.text().upper()
        if not key:
            return
        value = self.alias_input.text().strip()
        if value:
            names[key] = value
        else:
            names.pop(key, None)
        save_preferences(device_names=names)
        self.product_name.setText(value or model_info(self.display_model)["name"])

    def change_color(self, index):
        self.product_color = self.color_select.itemData(index)
        save_preferences(product_color=self.product_color)
        self.product_art.set_color(self.product_color)

    def change_startup(self, enabled):
        try:
            startup.set_enabled(enabled)
        except OSError as error:
            self.startup_toggle.setChecked(startup.enabled())
            self.show_message(str(error), True)

    def change_codec(self, *_):
        value = self.codec_select.currentData()
        if value in (0, 2) and QMessageBox.question(self, "Change audio codec?", "The device may briefly reconnect. Continue?") == QMessageBox.StandardButton.Yes:
            self.change("codec", value)
        else:
            self.render(self.state)

    def confirm_update(self):
        if QMessageBox.question(self, "Install update?", "Download the matching version, verify it, then restart?") == QMessageBox.StandardButton.Yes:
            self.updater.install()

    def find_bud(self, side):
        if model_info(self.display_model)["kind"] in ("headphones", "neckband"):
            side = 6
        if QMessageBox.question(self, "Play locator sound?", "Remove the device from your ears first. The sound stops after 15 seconds.") == QMessageBox.StandardButton.Yes:
            self.change("find", [side, True])
            QTimer.singleShot(15000, self.stop_ringing)

    def stop_ringing(self):
        profile = model_info(self.display_model)
        sides = [6] if profile["kind"] in ("headphones", "neckband") else [2] if profile.get("ring_legacy") else [2, 3]
        for side in sides:
            self.worker.submit("write", "find", [side, False])

    def refresh(self):
        self.audio.submit()
        if self.connection in ("connected", "demo") and "_refresh" not in self.pending:
            self.pending.add("_refresh")
            self.worker.submit("refresh")
        elif self.connection == "disconnected":
            self.worker.submit("devices")

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
        self.theme_timer.stop()
        self.bass_timer.stop()
        self.updater.close()
        self.worker.stop()
        if self.tray:
            self.tray.hide()
        event.accept()
        QTimer.singleShot(0, QApplication.instance().quit)
