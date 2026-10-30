import json
import os
from pathlib import Path
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from .variants import backend_path


def executable():
    override = os.environ.get("NOTHINGX_CORE")
    if override:
        return Path(override)
    return backend_path(Path(__file__).resolve().parent)


class NativeClient(QObject):
    event = Signal(dict)
    finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.read)
        self.process.finished.connect(self.on_finished)
        self.process.errorOccurred.connect(self.on_error)
        self.buffer = bytearray()
        self.waiting = []
        self.stopping = False
        self.kill_timer = QTimer(self)
        self.kill_timer.setSingleShot(True)
        self.kill_timer.timeout.connect(self.process.kill)
        self.process.finished.connect(self.kill_timer.stop)
        self.process.started.connect(self.flush)

    def start(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        env = QProcessEnvironment.systemEnvironment()
        if getattr(sys, "frozen", False):
            env.insert("NOTHINGX_BUNDLED", "1")
        self.process.setProcessEnvironment(env)
        self.process.start(str(executable()), [])

    def flush(self):
        waiting, self.waiting = self.waiting, []
        for request in waiting:
            self.send(request)

    def send(self, request):
        if self.stopping:
            return
        if self.process.state() != QProcess.ProcessState.Running:
            self.waiting.append(request)
            return
        self.process.write((json.dumps(request, separators=(",", ":")) + "\n").encode())

    def read(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        while b"\n" in self.buffer:
            line, _, rest = self.buffer.partition(b"\n")
            self.buffer = bytearray(rest)
            try:
                event = json.loads(line)
                if isinstance(event, dict):
                    self.event.emit(event)
            except (ValueError, UnicodeError):
                self.event.emit({"type": "message", "text": "Invalid response from the native backend.", "error": True})

    def on_error(self, error):
        if self.stopping:
            return
        reason = "Build the C++ backend with ./setup.sh." if error == QProcess.ProcessError.FailedToStart else self.process.errorString()
        self.event.emit({"type": "status", "phase": "disconnected", "detail": "Backend unavailable"})
        self.event.emit({"type": "message", "text": reason, "error": True})
        if error == QProcess.ProcessError.FailedToStart:
            self.finished.emit()

    def on_finished(self, *_):
        if not self.stopping:
            self.event.emit({"type": "state", "state": {}})
            self.event.emit({"type": "status", "phase": "disconnected", "detail": "Backend stopped"})
            self.event.emit({"type": "audio", "state": {"available": False, "error": "Backend stopped"}})
        self.finished.emit()

    def stop(self):
        if not self.stopping and self.process.state() != QProcess.ProcessState.NotRunning:
            self.send({"action": "quit"})
            self.process.closeWriteChannel()
            self.kill_timer.start(3000)
        self.stopping = True

    def is_running(self):
        return self.process.state() != QProcess.ProcessState.NotRunning
