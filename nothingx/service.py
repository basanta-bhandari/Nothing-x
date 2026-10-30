from collections import deque
import time

from PySide6.QtCore import QObject, QTimer, Signal

from .engine import Engine

READ_KEYS = ("battery", "anc", "eq", "low_latency", "bass", "spatial", "in_ear", "dual", "codec", "firmware", "model")
DEMO_PAYLOADS = {
    "model": [0x72, 0xB1], "battery": [3, 2, 92, 3, 88, 4, 76],
    "anc": [1, 4, 0, 2, 4, 0], "eq": [0, 0], "in_ear": [1, 1, 1],
    "low_latency": [2], "spatial": [0], "bass": [1, 6], "dual": [1], "codec": [0],
    "firmware": list(b"Demo 0.4.0"),
}


class Service(QObject):
    event = Signal(dict)
    finished = Signal()

    def __init__(self, backend="cpp", parent=None):
        super().__init__(parent)
        self.engine = Engine(backend)
        self.backend = backend
        self.phase = "disconnected"
        self.transport = None
        self.sequence = 0
        self.active = None
        self.requests = deque()
        self.refresh_keys = set()
        self.pending = set()
        self.last_state = {}
        self.demo = False
        self.closed = False
        self.ringing = {}
        self.address = ""
        self.ports = deque()
        self.deadline = 0
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.last_poll = time.monotonic()
        QTimer.singleShot(0, lambda: self.emit("ready", backend=backend, version="0.4.0"))

    def emit(self, kind, **values):
        self.event.emit({"type": kind, **values})

    def status(self, phase, detail):
        self.phase = phase
        self.emit("status", phase=phase, detail=detail)

    def state(self):
        return self.engine.call("state")

    def next_sequence(self):
        self.sequence = self.sequence % 255 + 1
        return self.sequence

    def feed(self, data):
        result = self.engine.call("feed", bytes=list(data))
        if result["state"] != self.last_state:
            self.last_state = result["state"]
            self.emit("state", state=self.last_state)
        for frame in result["frames"]:
            if self.active and frame["command"] == self.active["command"] and frame["sequence"] == self.active["sequence"]:
                self.complete(frame)
        return result

    def request(self, op, callback=None, timeout=.6, urgent=False, **values):
        sequence = self.next_sequence()
        packet = self.engine.call(op, sequence=sequence, **values)
        job = {"command": packet["command"], "sequence": sequence, "bytes": bytes(packet["bytes"]),
               "callback": callback, "timeout": timeout, "urgent": urgent}
        self.requests.appendleft(job) if urgent else self.requests.append(job)
        if urgent and self.active and not self.active["urgent"]:
            self.complete(None)
        self.pump()

    def pump(self):
        if self.active or not self.requests or not self.transport:
            return
        self.active = self.requests.popleft()
        self.active["deadline"] = time.monotonic() + self.active["timeout"]
        if self.transport.write(self.active["bytes"]) < 0:
            self.disconnect("Bluetooth write failed.")

    def complete(self, frame):
        if not self.active:
            return
        request, self.active = self.active, None
        if request["callback"]:
            request["callback"](frame)
        self.pump()

    def connect_device(self, address, channel=0):
        from PySide6.QtBluetooth import QBluetoothAddress
        if QBluetoothAddress(address).isNull() or not 0 <= channel <= 30:
            raise ValueError("Select a paired device or enter its Bluetooth address.")
        self.disconnect()
        self.address = address.upper()
        self.ports = deque([channel] if channel else [15, 16, 17, *range(1, 15), *range(18, 31)])
        self.status("connecting", "Connecting…")
        self.next_port()

    def next_port(self):
        from PySide6.QtBluetooth import QBluetoothAddress, QBluetoothServiceInfo, QBluetoothSocket
        previous, self.transport = self.transport, None
        if previous:
            previous.abort()
            previous.deleteLater()
        self.active = None
        self.requests.clear()
        if self.phase != "connecting":
            return
        if not self.ports:
            self.disconnect("Control connection unavailable. Connect the device in Bluetooth settings and close other companion apps.")
            return
        port = self.ports.popleft()
        socket = QBluetoothSocket(QBluetoothServiceInfo.Protocol.RfcommProtocol, self)
        self.transport = socket
        self.deadline = time.monotonic() + 1.2
        socket.connected.connect(lambda s=socket: self.socket_connected(s))
        socket.readyRead.connect(lambda s=socket: self.socket_read(s))
        socket.errorOccurred.connect(lambda error, s=socket: self.socket_error(s))
        socket.disconnected.connect(lambda s=socket: self.socket_error(s))
        from PySide6.QtCore import QIODevice
        socket.connectToService(QBluetoothAddress(self.address), port, QIODevice.OpenModeFlag.ReadWrite)

    def socket_connected(self, socket):
        if socket is not self.transport:
            return
        self.deadline = 0

        def handshake(frame):
            if frame is None:
                self.next_port()
                return
            self.request("packet", command=0xF001, payload=[], timeout=.18, urgent=True,
                         callback=lambda _: self.request("read", key="model", urgent=True, callback=self.model_read))

        self.request("packet", command=0xC001, payload=[], timeout=.8, callback=handshake)

    def model_read(self, frame):
        if self.phase != "connecting":
            return
        self.status("connected", "Connected")
        self.last_poll = time.monotonic()
        self.refresh()

    def socket_read(self, socket):
        if socket is self.transport:
            self.feed(bytes(socket.readAll()))

    def socket_error(self, socket):
        if socket is not self.transport:
            return
        if self.phase == "connecting":
            self.next_port()
        else:
            self.disconnect(socket.errorString())

    def disconnect(self, reason=""):
        socket, self.transport = self.transport, None
        if socket:
            for side in self.ringing:
                packet = self.engine.call("packet", command=0xF002, payload=[side, 0], sequence=self.next_sequence())
                socket.write(bytes(packet["bytes"]))
            socket.disconnectFromService()
            socket.deleteLater()
        self.ringing.clear()
        self.demo = False
        self.active = None
        self.requests.clear()
        self.refresh_keys.clear()
        for key in self.pending:
            self.emit("completed", key=key)
        self.pending.clear()
        self.engine.call("reset")
        self.last_state = {}
        self.emit("state", state={})
        self.status("disconnected", "Disconnected")
        if reason:
            self.emit("message", text=reason, error=True)

    def refresh(self):
        if self.demo:
            self.emit("state", state=self.state())
            self.emit("completed", key="_refresh")
            return
        if self.phase != "connected":
            self.emit("completed", key="_refresh")
            return
        for key in READ_KEYS:
            if key not in self.refresh_keys:
                self.refresh_keys.add(key)
                self.request("read", key=key, callback=lambda _, k=key: self.read_complete(k))

    def read_complete(self, key):
        self.refresh_keys.discard(key)
        if not self.refresh_keys:
            self.emit("completed", key="_refresh")

    def write(self, key, value):
        if self.phase not in ("connected", "demo"):
            raise ValueError("Connect your device first.")
        if key in self.pending and key != "find":
            raise ValueError("This setting is still being confirmed.")
        if self.demo:
            self.engine.call("write", key=key, value=value)
            if key != "find":
                self.demo_value(key, value)
            self.emit("completed", key=key)
            return
        self.pending.add(key)

        def written(frame):
            if key == "find":
                if value[1]:
                    self.ringing[value[0]] = time.monotonic() + 15
                else:
                    self.ringing.pop(value[0], None)
                self.finish_write(key, True)
            elif self.state().get(key) == value:
                self.finish_write(key, True)
            else:
                self.verify(key, value, 0)

        try:
            self.request("write", key=key, value=value, timeout=.16, urgent=True, callback=written)
        except Exception:
            self.pending.discard(key)
            self.emit("completed", key=key)
            raise

    def verify(self, key, value, attempt):
        def confirmed(frame):
            if self.state().get(key) == value:
                self.finish_write(key, True)
            elif attempt == 0:
                self.verify(key, value, 1)
            else:
                self.finish_write(key, False)
        self.request("read", key=key, timeout=.35 if attempt == 0 else .6, urgent=True, callback=confirmed)

    def finish_write(self, key, confirmed):
        self.pending.discard(key)
        self.emit("message", text="Updated" if confirmed else "The device did not confirm this setting. Showing the last reported value.", error=not confirmed)
        self.emit("completed", key=key)

    def start_demo(self):
        self.disconnect()
        self.demo = True
        for key, payload in DEMO_PAYLOADS.items():
            command = self.engine.call("read", key=key)["command"]
            self.feed(bytes(self.engine.call("packet", command=command, payload=payload)["bytes"]))
        self.status("demo", "Demo mode")

    def demo_value(self, key, value):
        from .protocol import ANC, EQ
        if key == "anc":
            payload = [1, ANC[value], 0, 2, ANC[value], 0]
        elif key == "eq":
            payload = [0, EQ[value]]
        elif key == "bass":
            payload = [int(value[0]), round(value[1] * 2)]
        elif key == "in_ear":
            payload = [1, 1, int(value)]
        elif key == "low_latency":
            payload = [1 if value else 2]
        else:
            payload = [int(value)]
        command = self.engine.call("read", key=key)["command"]
        self.feed(bytes(self.engine.call("packet", command=command, payload=payload)["bytes"]))

    def tick(self):
        now = time.monotonic()
        if self.phase == "connecting" and self.deadline and now >= self.deadline:
            self.next_port()
        if self.active and now >= self.active["deadline"]:
            self.complete(None)
        for side, deadline in tuple(self.ringing.items()):
            if now >= deadline:
                self.write("find", [side, False])
        if self.phase == "connected" and now - self.last_poll >= 25:
            self.last_poll = now
            if "battery" not in self.refresh_keys:
                self.request("read", key="battery")

    def submit(self, request):
        try:
            action = request.get("action")
            if action == "connect":
                self.connect_device(request.get("address", self.address), int(request.get("channel", 0)))
            elif action == "disconnect":
                self.disconnect()
            elif action == "write":
                self.write(request.get("key", ""), request.get("value"))
            elif action == "refresh":
                self.refresh()
            elif action == "demo":
                self.start_demo()
            elif action == "devices":
                self.emit("devices", devices=[])
            elif action == "quit":
                self.close()
            else:
                raise ValueError("Unsupported request.")
        except (ValueError, OSError, RuntimeError) as error:
            self.emit("message", text=str(error), error=True)
            if request.get("action") == "write":
                self.emit("completed", key=request.get("key", ""))

    def close(self):
        if not self.closed:
            self.disconnect()
            self.timer.stop()
            self.engine.close()
            self.closed = True
            self.finished.emit()
