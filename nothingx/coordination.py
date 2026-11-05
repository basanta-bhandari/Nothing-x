import json
import fcntl
import os
from pathlib import Path

from PySide6.QtCore import QObject
from PySide6.QtNetwork import QLocalServer


def socket_path(backend=None):
    root = Path(os.environ.get("NOTHINGX_RUNTIME_DIR", os.environ.get("XDG_RUNTIME_DIR", f"/tmp/nothingx-{os.getuid()}")))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    from .variants import backend_name
    return str(root / f"nothingx-service-v2-{backend_name(backend)}.sock")


class ServiceBroker(QObject):
    def __init__(self, service, submit=None, parent=None):
        super().__init__(parent)
        self.service = service
        self.submit = submit or service.submit
        self.clients = {}
        self.latest = {}
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        path = socket_path(service.backend)
        self.lock = open(path + ".lock", "a")
        self.available = False
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            self.lock = None
            return
        QLocalServer.removeServer(path)
        self.available = self.server.listen(path)
        if not self.available:
            self.lock.close()
            self.lock = None
            return
        self.service.finished.connect(self.close)
        self.server.newConnection.connect(self.accept)
        self.service.event.connect(self.broadcast)

    def send(self, peer, event):
        peer.write(json.dumps(event, separators=(",", ":")).encode() + b"\n")

    def accept(self):
        while self.server.hasPendingConnections():
            peer = self.server.nextPendingConnection()
            self.clients[peer] = bytearray()
            peer.readyRead.connect(lambda client=peer: self.read(client))
            peer.disconnected.connect(lambda client=peer: self.release(client))
            self.send(peer, {"type": "ready", "backend": self.service.backend, "shared": True, "address": self.service.address})
            self.send(peer, self.latest.get("state", {"type": "state", "state": self.service.state()}))
            self.send(peer, self.latest.get("status", {"type": "status", "phase": self.service.phase, "detail": "Connected" if self.service.phase == "connected" else "Disconnected"}))
            if self.service.audio.state:
                self.send(peer, {"type": "audio", "state": self.service.audio.state})
            if "devices" in self.latest:
                self.send(peer, self.latest["devices"])
            if peer.bytesAvailable():
                self.read(peer)

    def read(self, peer):
        if peer not in self.clients:
            return
        data = self.clients[peer]
        data.extend(bytes(peer.readAll()))
        if len(data) > 1024 * 1024:
            peer.abort()
            return
        while b"\n" in data:
            line, _, remaining = data.partition(b"\n")
            data[:] = remaining
            try:
                request = json.loads(line)
                if isinstance(request, dict) and request.get("action") not in ("quit", "demo"):
                    self.submit(request)
            except (ValueError, TypeError):
                self.send(peer, {"type": "message", "text": "Invalid control request.", "error": True})

    def broadcast(self, event):
        if event.get("type") in ("state", "status", "audio", "devices"):
            self.latest[event["type"]] = event
        for peer in tuple(self.clients):
            self.send(peer, event)

    def release(self, peer):
        self.clients.pop(peer, None)
        peer.deleteLater()

    def close(self):
        for peer in tuple(self.clients):
            peer.disconnectFromServer()
        self.server.close()
        if self.lock is not None:
            fcntl.flock(self.lock, fcntl.LOCK_UN)
            self.lock.close()
            self.lock = None
