import json
import os
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal


def percent(item):
    return round(max((v.get("value", 0) for v in item.get("volume", {}).values()), default=0) / 65536 * 100)


def endpoint(item):
    return {"name": item["name"], "index": item["index"], "description": item.get("description", item["name"]),
            "volume": percent(item), "mute": bool(item.get("mute")), "balance": round(float(item.get("balance", 0)) * 100),
            "channels": list(item.get("volume", {})), "codec": item.get("properties", {}).get("api.bluez5.codec", ""),
            "sample": item.get("sample_specification", ""), "running": item.get("state") == "RUNNING"}


class LinuxAudio(QObject):
    event = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.address = ""
        self.state = {}
        self.closed = False
        self.processes = set()
        self.querying = False
        self.dirty = False
        self.auto_headset = None
        self.pending = {}
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.refresh)
        self.subscriber = QProcess(self)
        self.subscriber.setProcessEnvironment(self.environment())
        self.subscriber.readyReadStandardOutput.connect(self.changed)
        self.subscriber.finished.connect(lambda *_: self.reconnect())
        self.retry = QTimer(self)
        self.retry.setSingleShot(True)
        self.retry.setInterval(4000)
        self.retry.timeout.connect(self.start)
        QTimer.singleShot(0, self.start)

    def environment(self):
        env = QProcessEnvironment.systemEnvironment()
        env.insert("LC_ALL", "C")
        if getattr(sys, "frozen", False):
            if env.contains("LD_LIBRARY_PATH_ORIG"):
                env.insert("LD_LIBRARY_PATH", env.value("LD_LIBRARY_PATH_ORIG"))
            else:
                env.remove("LD_LIBRARY_PATH")
        return env

    def run(self, program, args, callback):
        if self.closed:
            return
        process = QProcess(self)
        process.setProcessEnvironment(self.environment())
        timer = QTimer(process)
        timer.setSingleShot(True)
        timer.setInterval(3000)
        timer.timeout.connect(process.kill)
        self.processes.add(process)
        done = [False]

        def complete(code=-1, *_):
            if self.closed:
                self.processes.discard(process)
                return
            if done[0]:
                return
            done[0] = True
            timer.stop()
            output = bytes(process.readAllStandardOutput()).decode(errors="replace")
            error = bytes(process.readAllStandardError()).decode(errors="replace").strip()
            self.processes.discard(process)
            if not self.closed:
                callback(output, "" if code == 0 else error or process.errorString())
            process.deleteLater()

        process.finished.connect(complete)
        process.errorOccurred.connect(lambda error: complete() if error == QProcess.ProcessError.FailedToStart else None)
        process.start(program, args)
        timer.start()

    def start(self):
        if self.closed:
            return
        if self.subscriber.state() == QProcess.ProcessState.NotRunning:
            self.subscriber.start("pactl", ["subscribe"])
        self.run("wpctl", ["settings", "bluetooth.autoswitch-to-headset-profile"], self.headset_read)
        self.refresh()

    def headset_read(self, output, error):
        if not error:
            self.auto_headset = True if "Value: true" in output else False if "Value: false" in output else None

    def reconnect(self):
        if not self.closed:
            self.retry.start()

    def changed(self):
        self.subscriber.readAllStandardOutput()
        if not self.closed:
            self.timer.start()

    def refresh(self):
        if self.closed:
            return
        if self.querying:
            self.dirty = True
            return
        self.querying = True
        self.dirty = False
        self.pending = {}
        commands = {"info": ["info"], "cards": ["list", "cards"], "sinks": ["list", "sinks"],
                    "sources": ["list", "sources"], "streams": ["list", "sink-inputs"], "captures": ["list", "source-outputs"]}
        for key, args in commands.items():
            self.run("pactl", ["-f", "json", *args], lambda output, error, k=key: self.received(k, output, error))

    def received(self, key, output, error):
        try:
            value = json.loads(output) if not error else None
        except ValueError:
            value = None
        self.pending[key] = value
        if len(self.pending) < 6:
            return
        self.querying = False
        if any(value is None for value in self.pending.values()):
            self.state = {"available": False, "error": "Audio server unavailable. Start pipewire-pulse and WirePlumber."}
        else:
            self.state = self.normalize(self.pending)
        self.event.emit({"type": "audio", "state": self.state})
        if self.dirty:
            self.timer.start()

    def normalize(self, raw):
        matches = [c for c in raw["cards"] if c.get("properties", {}).get("device.api") == "bluez5"
                   and (c.get("properties", {}).get("api.bluez5.address", "").upper() == self.address
                        if self.address else any(name in c.get("properties", {}).get("device.description", "").lower() for name in ("nothing", "cmf", "ear (", "headphone")))]
        card = matches[0] if len(matches) == 1 else None
        sink = next((endpoint(s) for s in raw["sinks"] if card and s.get("properties", {}).get("device.name") == card["name"]), None)
        sources = [endpoint(s) for s in raw["sources"] if not s["name"].endswith(".monitor")]
        streams = []
        for kind, values in (("playback", raw["streams"]), ("recording", raw["captures"])):
            for stream in values:
                target = stream.get("sink" if kind == "playback" else "source")
                if target in (None, 4294967295):
                    continue
                props = stream.get("properties", {})
                streams.append({"kind": kind, "index": stream["index"], "name": props.get("application.name", props.get("media.name", "Audio stream")),
                                "media": props.get("media.name", ""), "volume": percent(stream), "mute": bool(stream.get("mute")), "target": target, "paused": bool(stream.get("corked"))})
        profiles = [{"name": name, "description": p.get("description", name)} for name, p in (card or {}).get("profiles", {}).items() if p.get("available") not in (False, "no", "not available")]
        return {"available": True, "server": raw["info"].get("server_name", "PipeWire"), "auto_headset": self.auto_headset,
                "default_sink": raw["info"].get("default_sink_name", ""), "default_source": raw["info"].get("default_source_name", ""),
                "card": {"name": card["name"], "profile": card.get("active_profile"), "profiles": profiles} if card else None,
                "sink": sink, "sinks": [endpoint(s) for s in raw["sinks"]], "sources": sources, "streams": streams,
                "capabilities": {"profiles": True, "balance": True, "streams": True, "microphones": True}}

    def request(self, key, value=None, target=None):
        if key == "address":
            self.address = str(value or "").upper()
            self.refresh()
            return
        if key == "refresh":
            self.refresh()
            return
        try:
            program, args = self.command(key, value, target)
        except ValueError as error:
            self.event.emit({"type": "message", "text": str(error), "error": True})
            self.event.emit({"type": "audio_completed", "key": key})
            return

        def completed(output, error):
            if error:
                self.event.emit({"type": "message", "text": error, "error": True})
            self.event.emit({"type": "audio_completed", "key": key})
            if key == "auto_headset":
                self.run("wpctl", ["settings", "bluetooth.autoswitch-to-headset-profile"], self.headset_read)
            self.timer.start()

        self.run(program, args, completed)

    def command(self, key, value, target):
        state = self.state
        sink, card = state.get("sink"), state.get("card")
        if key == "auto_headset" and type(value) is bool and state.get("auto_headset") is not None:
            return "wpctl", ["settings", "--save", "bluetooth.autoswitch-to-headset-profile", str(value).lower()]
        if key == "profile" and card and value in {p["name"] for p in card["profiles"]}:
            return "pactl", ["set-card-profile", card["name"], value]
        if key in ("output_volume", "output_mute", "balance", "default_output") and sink:
            if key == "default_output":
                return "pactl", ["set-default-sink", sink["name"]]
            if key == "output_mute" and type(value) is bool:
                return "pactl", ["set-sink-mute", sink["name"], str(int(value))]
            if key in ("balance", "output_volume") and type(value) is int:
                if key == "balance" and not -100 <= value <= 100 or key == "output_volume" and not 0 <= value <= 100:
                    raise ValueError("Audio value is outside its range.")
                volume = value if key == "output_volume" else sink["volume"]
                balance = (value if key == "balance" else sink["balance"]) / 100
                values = [round(volume * (1 - max(0, balance))), round(volume * (1 + min(0, balance)))] if sink["channels"] == ["front-left", "front-right"] else [volume]
                return "pactl", ["set-sink-volume", sink["name"], *(f"{v}%" for v in values)]
        if key in ("default_input", "input_volume", "input_mute"):
            source = next((s for s in state.get("sources", []) if s["name"] == target), None)
            if source:
                if key == "default_input":
                    return "pactl", ["set-default-source", target]
                if key == "input_volume" and type(value) is int and 0 <= value <= 100:
                    return "pactl", ["set-source-volume", target, f"{value}%"]
                if key == "input_mute" and type(value) is bool:
                    return "pactl", ["set-source-mute", target, str(int(value))]
        if key in ("stream_volume", "stream_mute", "stream_route"):
            stream = next((s for s in state.get("streams", []) if f'{s["kind"]}:{s["index"]}' == target), None)
            if stream:
                kind = "sink-input" if stream["kind"] == "playback" else "source-output"
                if key == "stream_volume" and type(value) is int and 0 <= value <= 100:
                    return "pactl", [f"set-{kind}-volume", str(stream["index"]), f"{value}%"]
                if key == "stream_mute" and type(value) is bool:
                    return "pactl", [f"set-{kind}-mute", str(stream["index"]), str(int(value))]
                destinations = state.get("sinks" if stream["kind"] == "playback" else "sources", [])
                if key == "stream_route" and value in {d["name"] for d in destinations}:
                    return "pactl", [f"move-{kind}", str(stream["index"]), value]
        raise ValueError("This audio control is not available for the current device.")

    def close(self):
        self.closed = True
        self.timer.stop()
        self.retry.stop()
        self.subscriber.kill()
        self.subscriber.waitForFinished(100)
        for process in tuple(self.processes):
            process.kill()
            process.waitForFinished(100)
        self.processes.clear()


class UnavailableAudio(QObject):
    event = Signal(dict)

    def refresh(self):
        self.event.emit({"type": "audio", "state": {"available": False, "error": "Audio integration is unavailable on this platform."}})

    def request(self, key, value=None, target=None):
        self.refresh()

    def close(self):
        pass


def make_audio(parent=None):
    if sys.platform == "darwin":
        from .macos_audio import MacAudio
        return MacAudio(parent)
    return LinuxAudio(parent) if sys.platform.startswith("linux") else UnavailableAudio(parent)
