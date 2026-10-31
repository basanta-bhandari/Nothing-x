from PySide6.QtCore import QObject, QTimer, Signal

from .variants import backend_name


class NativeClient(QObject):
    event = Signal(dict)
    finished = Signal()

    def __init__(self, parent=None, demo=False):
        super().__init__(parent)
        self.demo = demo
        self.handoff = None
        self.handoff_ready = demo
        self.service = None
        self.waiting = []
        self.stopping = False
        self.running = False

    def start(self):
        if self.running or self.stopping:
            return
        try:
            from .service import Service
            self.service = Service(backend_name(), self)
            self.service.event.connect(self.event)
            self.service.finished.connect(self.on_finished)
            self.running = True
            if self.demo:
                QTimer.singleShot(0, self.flush)
            else:
                from .coordination import HandoffClient
                self.handoff = HandoffClient(self)
                self.handoff.ready.connect(self.handoff_finished)
        except (ImportError, OSError, RuntimeError) as error:
            self.event.emit({"type": "status", "phase": "disconnected", "detail": "Backend unavailable"})
            self.event.emit({"type": "message", "text": f"Run ./setup.sh for the selected backend. {error}", "error": True})

    def handoff_finished(self):
        self.handoff_ready = True
        self.flush()

    def flush(self):
        waiting, self.waiting = self.waiting, []
        for request in waiting:
            self.send(request)

    def send(self, request):
        if self.stopping:
            return
        if not self.running or not self.handoff_ready:
            self.waiting.append(request)
            return
        QTimer.singleShot(0, lambda value=request: self.service.submit(value) if not self.stopping else None)

    def on_finished(self):
        self.running = False
        self.finished.emit()

    def stop(self):
        self.stopping = True
        if self.handoff:
            self.handoff.close()
        if self.service and not self.service.closed:
            self.service.close()
        else:
            self.on_finished()

    def is_running(self):
        return self.running
