
import queue
import re
import socket
import subprocess
import threading
import time

from PySide6.QtCore import QThread, Signal
from .protocol import Decoder, READS, encode, parse, write_command

MAC = re.compile(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\Z")


def paired_devices() -> list[tuple[str, str]]:
    try:
        result = subprocess.run(["bluetoothctl", "devices", "Paired"],
                                capture_output=True, text=True, timeout=8)
    except FileNotFoundError:
        raise RuntimeError("Install bluez-utils, then pair the earbuds in your Bluetooth settings.") from None
    if result.returncode:
        raise RuntimeError("BlueZ is unavailable. Start bluetooth.service and check that Bluetooth is enabled.")
    found = re.findall(r"^Device ((?:[\dA-Fa-f]{2}:){5}[\dA-Fa-f]{2}) (.+)$", result.stdout, re.M)
    return sorted(found, key=lambda x: ("cmf" not in x[1].lower(), x[1].lower()))


DEMO_STATE = {"model": "B172", "battery": {"left": {"level": 92, "charging": False},
              "right": {"level": 88, "charging": False}, "case": {"level": 76, "charging": False}},
              "anc": "Adaptive", "eq": "Dirac Opteo", "in_ear": True,
              "low_latency": False, "spatial": False, "bass": (True, 3),
              "dual": True, "codec": 0, "firmware": "Demo · 0.0.0"}


class Worker(QThread):
    state_changed = Signal(dict)
    status = Signal(str, str)
    message = Signal(str, bool)
    devices = Signal(list)
    completed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs = queue.Queue()
        self.stopping = threading.Event()
        self.cancelled = threading.Event()
        self.sock = None
        self.decoder = Decoder()
        self.sequence = 0
        self.state = {}
        self.demo = False
        self.linked = False
        self.ringing = set()

    def submit(self, action, *args):
        if action == "disconnect":
            self.cancelled.set()
        elif action in ("connect", "demo"):
            self.cancelled.clear()
        self.jobs.put((action, args))

    def stop(self):
        self.stopping.set()

    def _close(self):
        self.linked = False
        if self.sock:
            for side in self.ringing:
                try:
                    self.sock.sendall(encode(0xF002, bytes([side, 0])))
                except OSError:
                    pass
            self.sock.close()
            self.sock = None
        self.ringing.clear()
        self.decoder = Decoder()
        self.demo = False
        self.state = {}

    def _apply(self, frames):
        for frame in frames:
            update = parse(frame)
            if update:
                if "battery" in update:
                    update["battery"] = {**self.state.get("battery", {}), **update["battery"]}
                self.state.update(update)
                self.state_changed.emit(dict(self.state))

    def _receive(self):
        try:
            chunk = self.sock.recv(4096)
        except socket.timeout:
            return []
        if not chunk:
            raise ConnectionError("The earbuds closed the control connection.")
        frames = self.decoder.feed(chunk)
        self._apply(frames)
        return frames

    def _request(self, command, payload=b"", timeout=1.0):
        self.sequence = self.sequence % 255 + 1
        sequence = self.sequence
        self.sock.sendall(encode(command, payload, sequence))
        deadline = time.monotonic() + timeout
        while not self.stopping.is_set() and not self.cancelled.is_set() and time.monotonic() < deadline:
            for frame in self._receive():
                if frame.command == command and frame.sequence == sequence:
                    return frame
        return None

    def _connect(self, address, channel):
        self._close()
        self.state_changed.emit({})
        if not MAC.fullmatch(address):
            raise ValueError("Enter a Bluetooth address such as AA:BB:CC:DD:EE:FF.")
        self.status.emit("connecting", "Opening Bluetooth control connection…")
        candidates = [channel] if channel else [15, 16, 17, *range(1, 15), *range(18, 31)]
        last_error = "No Nothing protocol response"
        for candidate in candidates:
            if self.stopping.is_set():
                return
            if self.cancelled.is_set():
                raise ConnectionAbortedError("Connection cancelled.")
            self.status.emit("connecting", f"Checking RFCOMM channel {candidate}…")
            try:
                self.sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
                self.sock.settimeout(1.0)
                self.sock.connect((address, candidate))
                self.sock.settimeout(0.15)
                response = self._request(0xC001, timeout=1.0)
                if response is None:
                    raise TimeoutError("No valid Nothing protocol handshake")
                self._request(0xF001, timeout=0.8)
                self.linked = True
                self.message.emit(f"Control connection opened on channel {candidate}.", False)

                self._read("model")
                self.status.emit("connected", "Connected · reading device settings…")
                self._refresh()
                self.status.emit("connected", "Connected · settings read from earbuds")
                return
            except (OSError, ConnectionError) as exc:
                last_error = str(exc)
                if self.sock:
                    self.sock.close()
                    self.sock = None
                self.decoder = Decoder()
        raise ConnectionError(f"Could not open the earbuds: {last_error}. Pair/connect them in Bluetooth settings, close other companion apps, then try channel 15 or Auto.")

    def _read(self, key):
        command, payload = READS[key]
        response = self._request(command, payload)
        return parse(response).get(key) if response else None

    def _refresh(self):
        if self.demo:
            self.state_changed.emit(dict(self.state))
        elif self.linked:
            for key in READS:
                if self.stopping.is_set() or self.cancelled.is_set():
                    break
                self._read(key)

    def _write(self, key, value):
        try:
            command, payload = write_command(key, value)
            if not self.linked:
                raise ConnectionError("Connect your earbuds first.")
            if self.state.get("model") not in ("B172", "B187"):
                raise ValueError("Writes require a confirmed CMF Buds Pro 2 model (B172/B187).")
            if key != "find" and key not in self.state:
                raise ValueError("The device has not reported this setting.")
            if self.demo:
                if key != "find":
                    self.state[key] = value
                self.state_changed.emit(dict(self.state))
                self.message.emit("Demo setting updated · no Bluetooth commands sent", False)
                return
            self._request(command, payload, timeout=0.8)
            if key == "find":
                if value[1]:
                    self.ringing.add(value[0])
                else:
                    self.ringing.discard(value[0])
                self.message.emit("Locator command sent. Use Stop ringing to end the sound.", False)
                return
            if key == "codec":
                self.message.emit("Codec command sent. The earbuds may reconnect; reconnect here to verify the setting. Select LDAC in your audio settings afterward.", False)

            confirmed = False
            for delay in (1.2, 1.8):
                if self.stopping.wait(delay):
                    return
                if self._read(key) == value:
                    confirmed = True
                    break
            if not confirmed:
                self.message.emit("The device did not confirm the requested setting. The displayed value is the last reported device state.", True)
            else:
                self.message.emit("Setting confirmed by earbuds", False)
        finally:
            self.completed.emit(key)

    def run(self):
        last_poll = time.monotonic()
        while not self.stopping.is_set():
            try:
                try:
                    action, args = self.jobs.get(timeout=0.05)
                except queue.Empty:
                    action, args = "idle", ()
                if action == "connect":
                    self._connect(*args)
                elif action == "disconnect":
                    self._close()
                    self.state_changed.emit({})
                    self.status.emit("disconnected", "Control disconnected")
                elif action == "demo":
                    self._close()
                    self.demo = self.linked = True
                    self.state = dict(DEMO_STATE)
                    self.state_changed.emit(dict(self.state))
                    self.status.emit("demo", "Demo mode · simulated device")
                elif action == "devices":
                    try:
                        self.devices.emit(paired_devices())
                    except (RuntimeError, subprocess.TimeoutExpired) as exc:
                        self.message.emit(str(exc), True)
                elif action == "refresh":
                    try:
                        self._refresh()
                    finally:
                        self.completed.emit("_refresh")
                elif action == "write":
                    self._write(*args)
                elif self.linked and not self.demo:
                    self._receive()
                    if time.monotonic() - last_poll > 25:
                        self._read("battery")
                        self._read("anc")
                        last_poll = time.monotonic()
            except ValueError as exc:
                self.message.emit(str(exc), True)
            except (OSError, ConnectionError) as exc:
                self._close()
                self.state_changed.emit({})
                self.status.emit("disconnected", "Connection unavailable")
                self.message.emit(str(exc), True)
            except Exception as exc:
                self.message.emit(f"Control error: {exc}", True)
                self._close()
                self.state_changed.emit({})
                self.status.emit("disconnected", "Control error")
        self._close()
