import re

from PySide6.QtCore import QObject, Signal

MAC = re.compile(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\Z")


class Worker(QObject):
    state_changed = Signal(dict)
    status = Signal(str, str)
    message = Signal(str, bool)
    devices = Signal(list)
    completed = Signal(str)
    finished = Signal()

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client
        self.linked = False
        self.client.event.connect(self.receive)
        self.client.finished.connect(self.finished)

    def receive(self, event):
        kind = event.get("type")
        if kind == "state":
            state = dict(event.get("state", {}))
            if isinstance(state.get("bass"), list):
                state["bass"] = tuple(state["bass"])
            self.state_changed.emit(state)
        elif kind == "status":
            self.linked = event.get("phase") in ("connected", "demo")
            self.status.emit(event.get("phase", "disconnected"), event.get("detail", ""))
        elif kind == "message":
            self.message.emit(event.get("text", ""), bool(event.get("error")))
        elif kind == "devices":
            self.devices.emit(event.get("devices", []))
        elif kind == "completed":
            self.completed.emit(event.get("key", ""))

    def submit(self, action, *args):
        request = {"action": action}
        if action == "connect":
            request.update(address=args[0], channel=args[1] if len(args) > 1 else 0)
        elif action == "demo" and args:
            request["model"] = args[0]
        elif action == "write":
            request.update(key=args[0], value=args[1])
        self.client.send(request)

    def start(self):
        self.client.start()

    def stop(self):
        self.client.stop()

    def isRunning(self):
        return self.client.is_running()
