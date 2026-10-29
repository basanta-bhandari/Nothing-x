import json
import queue
import sys
import threading
import time

from PySide6.QtCore import QCoreApplication, QSettings, QTimer

from .backend import MAC, Worker


def main():
    app = QCoreApplication(sys.argv[:1])
    settings = QSettings("NothingXLinux", "NothingXLinux")
    worker = Worker()
    commands = queue.SimpleQueue()
    state = {"address": str(settings.value("address", "")), "desired": True,
             "phase": "disconnected", "devices": [], "next_retry": 0.0}

    def emit(kind, **values):
        print(json.dumps({"type": kind, **values}, separators=(",", ":")), flush=True)

    def on_status(phase, detail):
        state["phase"] = phase
        if phase == "disconnected":
            state["next_retry"] = time.monotonic() + 15
        emit("status", phase=phase, detail=detail)

    def on_devices(devices):
        state["devices"] = devices
        emit("devices", devices=devices)
        if not state["desired"] or state["phase"] != "disconnected":
            return
        address = state["address"]
        if not MAC.fullmatch(address):
            matches = [mac for mac, name in devices if "cmf" in name.lower() and "pro 2" in name.lower()]
            if len(matches) != 1:
                emit("message", text="Pair CMF Buds Pro 2 in Bluetooth settings.", error=True)
                return
            address = matches[0]
            state["address"] = address
            settings.setValue("address", address)
        state["phase"] = "connecting"
        worker.submit("connect", address, 0)

    worker.state_changed.connect(lambda value: emit("state", state=value))
    worker.status.connect(on_status)
    worker.message.connect(lambda text, error: emit("message", text=text, error=error))
    worker.devices.connect(on_devices)
    worker.completed.connect(lambda key: emit("completed", key=key))

    def read_input():
        for line in sys.stdin:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    commands.put(value)
            except (ValueError, TypeError):
                commands.put({"action": "invalid"})
        commands.put({"action": "quit"})

    def drain():
        while True:
            try:
                command = commands.get_nowait()
            except queue.Empty:
                break
            action = command.get("action")
            if action == "quit":
                app.quit()
                return
            if action == "connect":
                state["desired"] = True
                state["next_retry"] = 0
                if state["phase"] == "disconnected":
                    worker.submit("devices")
            elif action == "disconnect":
                state["desired"] = False
                worker.submit("disconnect")
            elif action == "refresh":
                worker.submit("refresh" if worker.linked else "devices")
            elif action == "write":
                key, value = command.get("key"), command.get("value")
                if key == "bass" and isinstance(value, list):
                    value = tuple(value)
                if key in ("anc", "eq", "spatial", "low_latency", "in_ear", "dual", "bass"):
                    worker.submit("write", key, value)
                else:
                    emit("message", text="Unsupported setting.", error=True)
            else:
                emit("message", text="Invalid applet request.", error=True)
        if state["desired"] and state["phase"] == "disconnected" and time.monotonic() >= state["next_retry"]:
            state["next_retry"] = time.monotonic() + 15
            worker.submit("devices")

    poll = QTimer()
    poll.timeout.connect(drain)
    poll.start(100)
    refresh = QTimer()
    refresh.timeout.connect(lambda: worker.submit("refresh") if worker.linked else None)
    refresh.start(30000)
    threading.Thread(target=read_input, daemon=True).start()
    worker.start()
    emit("ready")
    worker.submit("devices")
    result = app.exec()
    worker.stop()
    worker.wait(3000)
    return result


if __name__ == "__main__":
    sys.exit(main())
