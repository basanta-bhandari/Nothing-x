import os
from pathlib import Path
import socket

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


def socket_path():
    root = Path(os.environ.get("XDG_RUNTIME_DIR", f"/tmp/nothingx-{os.getuid()}"))
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return str(root / "nothingx-applet.sock")


class HandoffServer(QObject):
    def __init__(self, service, state, parent=None):
        super().__init__(parent)
        self.service, self.state = service, state
        self.holders = set()
        self.restore = False
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        path = socket_path()
        if not self.server.listen(path):
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.settimeout(.1)
            try:
                probe.connect(path)
            except OSError:
                QLocalServer.removeServer(path)
                self.server.listen(path)
            finally:
                probe.close()
        self.available = self.server.isListening()
        self.server.newConnection.connect(self.accept)

    def accept(self):
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            client.readyRead.connect(lambda peer=client: self.read(peer))
            client.disconnected.connect(lambda peer=client: self.release(peer))

    def read(self, peer):
        if bytes(peer.readAll()).strip() != b"hold" or peer in self.holders:
            return
        if not self.holders:
            self.restore = self.state["desired"]
            self.state["desired"] = False
            if self.service.phase != "disconnected":
                self.service.disconnect()
        self.holders.add(peer)
        peer.write(b"held\n")
        peer.flush()

    def release(self, peer):
        self.holders.discard(peer)
        peer.deleteLater()
        if not self.holders and self.restore:
            self.restore = False
            self.state["desired"] = True
            self.state["next_retry"] = 0
            self.service.discovery.refresh()


class HandoffClient(QObject):
    ready = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.finished = False
        self.socket = QLocalSocket(self)
        self.socket.connected.connect(lambda: self.socket.write(b"hold\n"))
        self.socket.readyRead.connect(self.received)
        self.socket.errorOccurred.connect(lambda _: self.finish())
        QTimer.singleShot(0, lambda: self.socket.connectToServer(socket_path()))
        QTimer.singleShot(500, self.finish)

    def received(self):
        if bytes(self.socket.readAll()).strip() == b"held":
            self.finish()

    def finish(self):
        if not self.finished:
            self.finished = True
            self.ready.emit()

    def close(self):
        self.socket.disconnectFromServer()
