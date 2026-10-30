from PySide6.QtCore import QObject, Signal


class AudioWorker(QObject):
    state_changed = Signal(dict)
    message = Signal(str, bool)
    completed = Signal(str)
    finished = Signal()

    def __init__(self, client, address="", parent=None):
        super().__init__(parent)
        self.client = client
        self.state = {}
        self._address = address
        self.client.event.connect(self.receive)
        self.client.finished.connect(self.finished)
        if address:
            self.address = address

    @property
    def address(self):
        return self._address

    @address.setter
    def address(self, value):
        self._address = value
        self.submit("address", value)

    def receive(self, event):
        if event.get("type") == "audio":
            self.state = event.get("state", {})
            self.state_changed.emit(self.state)
        elif event.get("type") == "audio_completed":
            self.completed.emit(event.get("key", ""))

    def submit(self, action="refresh", value=None, target=None):
        self.client.send({"action": "audio", "key": action, "value": value, "target": target})

    def start(self):
        self.client.start()

    def stop(self):
        pass

    def isRunning(self):
        return False
