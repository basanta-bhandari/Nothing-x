import json
import os
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtNetwork import QLocalSocket

from .variants import backend_name


class NativeClient(QObject):
    event = Signal(dict)
    finished = Signal()

    def __init__(self, parent=None, demo=False):
        super().__init__(parent)
        self.demo = demo
        self.service = None
        self.socket = None
        self.input = bytearray()
        self.waiting = []
        self.stopping = False
        self.running = False
        self.starting = False
        self.remote = False
        self.spawned = False
        self.deadline = 0
        self.retry = QTimer(self)
        self.retry.setSingleShot(True)
        self.retry.setInterval(150)
        self.retry.timeout.connect(self.connect_service)

    def start(self):
        if self.running or self.starting or self.stopping:
            return
        self.starting = True
        if self.demo:
            self.start_demo_service()
            return
        self.deadline = time.monotonic() + 8
        self.socket = QLocalSocket(self)
        self.socket.connected.connect(self.connected)
        self.socket.readyRead.connect(self.receive)
        self.socket.errorOccurred.connect(self.remote_error)
        self.socket.disconnected.connect(self.remote_closed)
        self.connect_service()

    def connect_service(self):
        if self.stopping or self.running:
            return
        if time.monotonic() >= self.deadline:
            self.starting = False
            self.event.emit({"type": "status", "phase": "disconnected", "detail": "Control service unavailable"})
            self.event.emit({"type": "message", "text": "The control service could not start. Reopen Nothing X to retry.", "error": True})
            return
        from .coordination import socket_path
        self.socket.abort()
        self.socket.connectToServer(socket_path())

    def connected(self):
        if self.stopping:
            return
        self.retry.stop()
        self.remote = True
        self.running = True
        self.starting = False
        self.flush()

    def receive(self):
        self.input.extend(bytes(self.socket.readAll()))
        if len(self.input) > 1024 * 1024:
            self.socket.abort()
            return
        while b"\n" in self.input:
            line, _, rest = self.input.partition(b"\n")
            self.input[:] = rest
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    self.event.emit(event)
            except ValueError:
                pass

    def remote_error(self, *_):
        if self.stopping or self.remote:
            return
        if not self.spawned:
            self.spawn_service()
        self.retry.start()

    def remote_closed(self):
        if self.remote and not self.stopping:
            self.running = False
            self.remote = False
            self.starting = True
            self.spawned = False
            self.input.clear()
            self.deadline = time.monotonic() + 8
            self.event.emit({"type": "status", "phase": "disconnected", "detail": "Reconnecting to controls…"})
            self.retry.start()

    def spawn_service(self):
        self.spawned = True
        backend = backend_name()
        root = Path(__file__).resolve().parents[1]
        if getattr(sys, "frozen", False):
            command = [os.environ.get("APPIMAGE", sys.executable), "--service-backend", backend]
        else:
            command = [sys.executable, "-m", "nothingx.service_entry", "--backend", backend, "--daemon", "--auto"]
        env = {key: value for key, value in os.environ.items() if not key.startswith("_PYI_")}
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        log = Path.home() / ("Library/Logs/NothingX" if sys.platform == "darwin" else ".cache/nothingx") / "service.log"
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a") as output:
                subprocess.Popen(command, cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as error:
            self.event.emit({"type": "message", "text": f"Could not start controls: {error}", "error": True})

    def start_demo_service(self):
        try:
            from .service import Service
            self.service = Service(backend_name(), self)
            self.service.event.connect(self.event)
            self.service.finished.connect(self.on_finished)
            self.running = True
            self.starting = False
            QTimer.singleShot(0, self.flush)
        except (ImportError, OSError, RuntimeError) as error:
            self.starting = False
            self.event.emit({"type": "message", "text": str(error), "error": True})

    def flush(self):
        waiting, self.waiting = self.waiting, []
        for request in waiting:
            self.send(request)

    def send(self, request):
        if self.stopping:
            return
        if not self.running:
            if request.get("action") in ("write", "audio") and (request.get("action") == "write" or request.get("key") not in ("address", "refresh")):
                self.event.emit({"type": "message", "text": "Controls are reconnecting. Try again once connected.", "error": True})
                self.event.emit({"type": "completed" if request.get("action") == "write" else "audio_completed", "key": request.get("key", "")})
                return
            if request in self.waiting:
                return
            if len(self.waiting) >= 128:
                self.event.emit({"type": "message", "text": "Controls are busy. Try again shortly.", "error": True})
                return
            self.waiting.append(request)
            if not self.starting:
                self.spawned = False
                self.deadline = time.monotonic() + 8
                if self.socket is None:
                    self.start()
                else:
                    self.starting = True
                    self.retry.start()
            return
        if self.remote:
            self.socket.write(json.dumps(request, separators=(",", ":")).encode() + b"\n")
        else:
            QTimer.singleShot(0, lambda value=request: self.service.submit(value) if not self.stopping else None)

    def on_finished(self):
        self.running = False
        self.finished.emit()

    def stop(self):
        if self.stopping:
            return
        self.stopping = True
        self.retry.stop()
        if self.socket:
            self.socket.abort()
        if self.service and not self.service.closed:
            self.service.close()
        else:
            self.on_finished()

    def is_running(self):
        return self.running
