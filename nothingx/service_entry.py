import argparse
import json
import os
import sys
import threading
import time


def main(arguments=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("rust",), default="rust")
    parser.add_argument("--auto", action="store_true")
    parser.add_argument("--daemon", action="store_true")
    args = parser.parse_args(arguments)
    if sys.platform == "darwin":
        os.environ.setdefault("QT_EVENT_DISPATCHER_CORE_FOUNDATION", "1")
    from PySide6.QtCore import QCoreApplication, QObject, QTimer, Signal
    from .service import Service
    from .preferences import read_preferences
    from .coordination import ServiceBroker
    app = QCoreApplication(sys.argv[:1])
    service = Service(args.backend)
    state = {"desired": args.auto, "address": read_preferences().get("address", ""), "next_retry": 0.0}

    class Input(QObject):
        command = Signal(dict)

    incoming = Input()

    def handle(request):
        action = request.get("action")
        if action == "connect" and not broker.available:
            service.emit("message", text="Another Nothing X panel applet is already running.", error=True)
            return
        if action == "connect" and not request.get("address"):
            if service.phase in ("connected", "connecting"):
                service.emit("state", state=service.state())
                service.status(service.phase, "Connected" if service.phase == "connected" else "Connecting…")
                return
            state["desired"] = True
            state["next_retry"] = 0
            service.discovery.refresh()
        else:
            if action == "connect":
                state["desired"] = True
                state["address"] = request.get("address", state["address"])
            if action == "disconnect":
                state["desired"] = False
            service.submit(request)

    def output(event):
        if not args.daemon:
            print(json.dumps(event, separators=(",", ":")), flush=True)
        elif event.get("type") == "message" and event.get("error"):
            print(event.get("text", ""), flush=True)
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

    broker = ServiceBroker(service, handle, service)
    if not broker.available:
        service.close()
        if args.daemon:
            return 0
        from .core import NativeClient
        relay = NativeClient(app)
        relay.event.connect(lambda event: print(json.dumps(event, separators=(",", ":")), flush=True))
        def forward(request):
            if request.get("action") == "quit":
                relay.stop()
                app.quit()
            else:
                relay.send(request)
        incoming.command.connect(forward)
        relay.start()
        threading.Thread(target=reader, daemon=True).start()
        return app.exec()
    service.event.connect(output)
    service.finished.connect(app.quit)
    incoming.command.connect(handle)
    retry = QTimer()
    retry.setInterval(15000)
    retry.timeout.connect(lambda: service.discovery.refresh() if state["desired"] and read_preferences().get("auto_reconnect", True) and service.phase == "disconnected" else None)
    retry.start()
    if args.auto and broker.available and read_preferences().get("auto_reconnect", True):
        QTimer.singleShot(0, service.discovery.refresh)
    elif not broker.available:
        QTimer.singleShot(0, lambda: service.emit("message", text="Another Nothing X panel applet is already running.", error=True))
    if not args.daemon:
        threading.Thread(target=reader, daemon=True).start()
    else:
        idle_since = [None]
        def idle_check():
            if broker.clients:
                idle_since[0] = None
            elif idle_since[0] is None:
                idle_since[0] = time.monotonic()
            elif time.monotonic() - idle_since[0] >= 30:
                broker.close()
                service.close()
                app.quit()
        idle = QTimer(service)
        idle.setInterval(5000)
        idle.timeout.connect(idle_check)
        idle.start()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
