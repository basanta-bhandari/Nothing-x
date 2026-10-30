import argparse
import json
import os
import sys
import threading
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("cpp", "rust"), default=os.environ.get("NOTHINGX_BACKEND", "cpp"))
    parser.add_argument("--auto", action="store_true")
    args = parser.parse_args()
    if sys.platform == "darwin":
        os.environ.setdefault("QT_EVENT_DISPATCHER_CORE_FOUNDATION", "1")
    from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal
    from .service import Service
    from .preferences import read_preferences
    app = QCoreApplication(sys.argv[:1])
    service = Service(args.backend)
    state = {"desired": args.auto, "address": read_preferences().get("address", ""), "next_retry": 0.0}

    class Input(QObject):
        command = Signal(dict)

    incoming = Input()

    def handle(request):
        action = request.get("action")
        if action == "connect" and not request.get("address"):
            state["desired"] = True
            state["next_retry"] = 0
            service.discovery.refresh()
        else:
            if action == "disconnect":
                state["desired"] = False
            service.submit(request)

    def output(event):
        print(json.dumps(event, separators=(",", ":")), flush=True)
        if event.get("type") == "status" and event.get("phase") == "disconnected":
            state["next_retry"] = time.monotonic() + 15
        if event.get("type") == "devices" and state["desired"] and service.phase == "disconnected" and time.monotonic() >= state["next_retry"]:
            matches = [(address, name) for address, name in event.get("devices", []) if service.discovery.matches(name) and address.upper() in service.discovery.connected]
            selected = next((device for device in matches if device[0].upper() == state["address"].upper()), matches[0] if len(matches) == 1 else None)
            if selected:
                state["address"] = selected[0]
                service.audio.request("address", selected[0])
                service.submit({"action": "connect", "address": selected[0]})

    def reader():
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if isinstance(request, dict):
                    incoming.command.emit(request)
            except ValueError:
                pass
        incoming.command.emit({"action": "quit"})

    service.event.connect(output)
    service.finished.connect(app.quit)
    incoming.command.connect(handle)
    retry = QTimer()
    retry.setInterval(15000)
    retry.timeout.connect(lambda: service.discovery.refresh() if state["desired"] and service.phase == "disconnected" else None)
    retry.start()
    if args.auto:
        QTimer.singleShot(0, service.discovery.refresh)
    threading.Thread(target=reader, daemon=True).start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
