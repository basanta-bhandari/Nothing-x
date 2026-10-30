from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QSlider, QLayout

from .ui import label, button, card, Switch


class AudioPage(QWidget):
    def __init__(self, worker):
        super().__init__()
        self.worker = worker
        self.state = {}
        self.updating = False
        self.stream_shape = None
        self.stream_widgets = {}
        self.box = QVBoxLayout(self)
        self.box.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(16)
        self.summary = label("Reading audio devices…", "muted", True)
        self.box.addWidget(self.summary)
        profile, layout = card("Bluetooth audio")
        self.profile = QComboBox()
        self.profile.setAccessibleName("Bluetooth audio profile and codec")
        self.profile.activated.connect(lambda: self.worker.submit("profile", self.profile.currentData()))
        layout.addWidget(self.profile)
        self.format = label("—", "muted", True)
        layout.addWidget(self.format)
        self.profile_hint = label("", "muted", True)
        layout.addWidget(self.profile_hint)
        self.auto_headset_row = QWidget()
        self.auto_headset_row.setStyleSheet("background: transparent;")
        headset_row = QHBoxLayout(self.auto_headset_row)
        headset_row.setContentsMargins(0, 0, 0, 0)
        headset_row.addWidget(label("Allow headset mode for the buds’ microphone", wrap=True), 1)
        self.auto_headset = Switch()
        self.auto_headset.setAccessibleName("Allow automatic headset mode for Bluetooth microphones")
        headset_row.addWidget(self.auto_headset)
        self.auto_headset.clicked.connect(lambda value: self.worker.submit("auto_headset", value))
        self.auto_headset.setToolTip("WirePlumber setting for all Bluetooth headsets. Headset mode reduces playback quality.")
        layout.addWidget(self.auto_headset_row)
        self.box.addWidget(profile)
        output, layout = card("Earbud output")
        self.output_volume = self.slider(layout, "Volume", 0, 100, lambda value: self.worker.submit("output_volume", value))
        self.balance = self.slider(layout, "Balance", -100, 100, lambda value: self.worker.submit("balance", value), balance=True)
        line = QHBoxLayout()
        self.output_mute = Switch("Mute")
        self.output_mute.clicked.connect(lambda value: self.worker.submit("output_mute", value))
        line.addWidget(self.output_mute)
        line.addStretch()
        self.default_output = button("Use as default output", lambda: self.worker.submit("default_output"))
        self.default_output.setMinimumHeight(38)
        line.addWidget(self.default_output)
        layout.addLayout(line)
        self.box.addWidget(output)
        microphone, layout = card("Microphone")
        self.input = QComboBox()
        self.input.setAccessibleName("Default microphone")
        self.input.activated.connect(lambda: self.worker.submit("default_input", target=self.input.currentData()))
        layout.addWidget(self.input)
        self.input_volume = self.slider(layout, "Input volume", 0, 100,
                                        lambda value: self.worker.submit("input_volume", value, self.input.currentData()))
        self.input_mute = Switch("Mute microphone")
        self.input_mute.clicked.connect(lambda value: self.worker.submit("input_mute", value, self.input.currentData()))
        layout.addWidget(self.input_mute)
        self.box.addWidget(microphone)
        applications, self.apps = card("Applications")
        self.box.addWidget(applications)
        self.box.addStretch()
        self.worker.state_changed.connect(self.render)

    def slider(self, layout, title, minimum, maximum, callback, balance=False):
        line = QHBoxLayout()
        line.addWidget(label(title))
        value_label = label("—", "muted")
        line.addStretch()
        line.addWidget(value_label)
        layout.addLayout(line)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setMinimumHeight(26)
        slider.setAccessibleName(title)
        timer = QTimer(slider)
        timer.setSingleShot(True)
        timer.setInterval(75)
        timer.timeout.connect(lambda: callback(slider.value()))

        def changed(value):
            value_label.setText(("Center" if value == 0 else f'{abs(value)}% {"right" if value > 0 else "left"}') if balance else f"{value}%")
            if not self.updating:
                timer.start()

        def released():
            if timer.isActive():
                timer.stop()
                callback(slider.value())

        slider.valueChanged.connect(changed)
        slider.sliderReleased.connect(released)
        slider._value_label = value_label
        slider._update_label = changed
        layout.addWidget(slider)
        return slider

    def sync_slider(self, slider, value, enabled=True):
        slider.setEnabled(enabled)
        if not slider.isSliderDown():
            slider.setValue(max(slider.minimum(), min(slider.maximum(), value)))
            slider._update_label(slider.value())

    def combo(self, combo, options, selected):
        entries = [(combo.itemText(i), combo.itemData(i)) for i in range(combo.count())]
        if entries != options:
            combo.clear()
            for title, value in options:
                combo.addItem(title, value)
        combo.setCurrentIndex(combo.findData(selected))
        combo.setEnabled(bool(options))

    def render(self, state):
        self.updating = True
        self.state = state
        available = bool(state.get("available"))
        self.summary.setText(state.get("server", "Audio") if available else state.get("error", "Audio server unavailable"))
        card_state, sink = state.get("card") or {}, state.get("sink") or {}
        self.combo(self.profile, [(p["description"], p["name"]) for p in card_state.get("profiles", [])], card_state.get("profile"))
        if not card_state and available:
            self.profile.addItem("Connect CMF Buds Pro 2 in Bluetooth settings")
            self.profile.setEnabled(False)
        self.format.setText(f'{sink.get("codec", "").upper()} · {sink.get("sample", "")}' if sink else "Audio output inactive")
        headset = str(card_state.get("profile", "")).startswith("headset")
        self.profile_hint.setText("Headset mode: microphone available, reduced playback quality." if headset else "A2DP provides stereo playback. LDAC appears here after enabling it in Device settings.")
        self.auto_headset_row.setVisible(state.get("auto_headset") is not None)
        self.auto_headset.setChecked(bool(state.get("auto_headset")))
        self.sync_slider(self.output_volume, sink.get("volume", 0), bool(sink))
        self.sync_slider(self.balance, sink.get("balance", 0), sink.get("channels") == ["front-left", "front-right"])
        self.output_mute.setEnabled(bool(sink))
        self.output_mute.setChecked(bool(sink.get("mute")))
        default = bool(sink) and sink.get("name") == state.get("default_sink")
        self.default_output.setText("Default output" if default else "Use as default output")
        self.default_output.setEnabled(bool(sink) and not default)
        sources = state.get("sources", [])
        self.combo(self.input, [(s["description"], s["name"]) for s in sources], state.get("default_source"))
        source = next((s for s in sources if s["name"] == state.get("default_source")), {})
        self.sync_slider(self.input_volume, source.get("volume", 0), bool(source))
        self.input_mute.setEnabled(bool(source))
        self.input_mute.setChecked(bool(source.get("mute")))
        shape = ([(s["kind"], s["index"]) for s in state.get("streams", [])],
                 [(s["name"], s["description"]) for s in state.get("sinks", [])],
                 [(s["name"], s["description"]) for s in sources])
        if shape != self.stream_shape:
            self.stream_shape = shape
            while self.apps.count() > 1:
                item = self.apps.takeAt(1)
                if item.widget():
                    for timer in item.widget().findChildren(QTimer):
                        timer.stop()
                    item.widget().deleteLater()
            self.stream_widgets = {}
            if not state.get("streams"):
                self.apps.addWidget(label("No application audio streams", "muted"))
            for stream in state.get("streams", []):
                self.add_stream(stream)
        for stream in state.get("streams", []):
            key = f'{stream["kind"]}:{stream["index"]}'
            title, volume, mute, route = self.stream_widgets[key]
            title.setText(f'{stream["name"]} · {"Playback" if stream["kind"] == "playback" else "Recording"}' + (" · Paused" if stream["paused"] else ""))
            title.setToolTip(stream["media"])
            self.sync_slider(volume, stream["volume"])
            mute.setChecked(stream["mute"])
            destinations = state.get("sinks" if stream["kind"] == "playback" else "sources", [])
            current = next((s["name"] for s in destinations if s["index"] == stream["target"]), None)
            self.combo(route, [(s["description"], s["name"]) for s in destinations], current)
        self.updating = False

    def add_stream(self, stream):
        key = f'{stream["kind"]}:{stream["index"]}'
        item = QWidget()
        item.setStyleSheet("background: transparent;")
        box = QVBoxLayout(item)
        box.setContentsMargins(0, 5, 0, 10)
        title = label("")
        box.addWidget(title)
        volume = self.slider(box, "Volume", 0, 100, lambda value, k=key: self.worker.submit("stream_volume", value, k))
        row = QHBoxLayout()
        mute = Switch("Mute")
        mute.clicked.connect(lambda value, k=key: self.worker.submit("stream_mute", value, k))
        row.addWidget(mute)
        route = QComboBox()
        route.setAccessibleName(f'{stream["name"]} audio destination')
        route.activated.connect(lambda index, k=key, combo=route: self.worker.submit("stream_route", combo.itemData(index), k))
        row.addWidget(route, 1)
        box.addLayout(row)
        self.apps.addWidget(item)
        self.stream_widgets[key] = (title, volume, mute, route)
