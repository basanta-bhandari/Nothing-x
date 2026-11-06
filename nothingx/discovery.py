import re
import os
import sys
import asyncio
import threading

from PySide6.QtCore import QObject, QCoreApplication, QProcess, QTimer, QBluetoothPermission, Qt, Signal


class Discovery(QObject):
    devices = Signal(list)
    message = Signal(str, bool)
    bus_result = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.connected = set()
        self.closed = False
        self.bus_busy = False
        self.bus_result.connect(self.deliver_bus_devices)

    def permission(self, callback):
        if sys.platform != "darwin":
            callback(True)
            return
        app = QCoreApplication.instance()
        permission = QBluetoothPermission()
        permission.setCommunicationModes(QBluetoothPermission.CommunicationMode.Access)
        status = app.checkPermission(permission)
        if status == Qt.PermissionStatus.Undetermined:
            app.requestPermission(permission, self, lambda result: callback(result.status() == Qt.PermissionStatus.Granted))
        else:
            callback(status == Qt.PermissionStatus.Granted)

    def refresh(self):
        if not self.closed:
            self.permission(self.scan)

    def scan(self, granted):
        if self.closed:
            return
        if not granted:
            self.message.emit("Allow Bluetooth access for Nothing X in macOS System Settings → Privacy & Security → Bluetooth.", True)
            self.devices.emit([])
            return
        if sys.platform == "darwin":
            self.mac_devices()
            return
        if os.environ.get("FLATPAK_ID"):
            self.bus_devices()
            return
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            return
        process = QProcess(self)
        self.process = process
        timer = QTimer(process)
        timer.setSingleShot(True)
        timer.setInterval(5000)
        timer.timeout.connect(process.kill)
        finished = [False]

        def done(code, *_):
            if finished[0]:
                return
            finished[0] = True
            timer.stop()
            if self.process is process:
                self.process = None
            if self.closed:
                process.deleteLater()
                return
            output = bytes(process.readAllStandardOutput()).decode(errors="replace")
            devices = re.findall(r"^Device ([0-9A-Fa-f:]{17}) (.+)$", output, re.M)
            devices = sorted(devices, key=lambda item: (not self.matches(item[1]), item[1].lower()))
            try:
                from PySide6.QtBluetooth import QBluetoothLocalDevice
                self.connected = {address.toString().upper() for address in QBluetoothLocalDevice().connectedDevices()}
            except RuntimeError:
                self.connected = set()
            self.devices.emit(devices)
            if code:
                self.message.emit("BlueZ is unavailable. Start bluetooth.service and pair your device in Bluetooth settings.", True)
            process.deleteLater()

        process.finished.connect(done)
        process.errorOccurred.connect(lambda error: done(-1) if error == QProcess.ProcessError.FailedToStart else None)
        process.start("bluetoothctl", ["devices", "Paired"])
        timer.start()

    def mac_devices(self):
        try:
            from IOBluetooth import IOBluetoothDevice
            devices = []
            self.connected = set()
            for device in IOBluetoothDevice.pairedDevices() or []:
                address = str(device.getAddressString()).replace("-", ":").upper()
                devices.append((address, str(device.name() or address)))
                if device.isConnected():
                    self.connected.add(address)
            self.devices.emit(sorted(devices, key=lambda item: (not self.matches(item[1]), item[1])))
        except (ImportError, RuntimeError) as error:
            self.message.emit(f"Bluetooth device listing unavailable: {error}. You can enter the device address manually.", True)
            self.devices.emit([])

    def bus_devices(self):
        if self.bus_busy:
            return
        self.bus_busy = True

        async def scan():
            from dbus_next import BusType, Message, MessageType
            from dbus_next.aio import MessageBus
            bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
            try:
                reply = await bus.call(Message(destination="org.bluez", path="/", interface="org.freedesktop.DBus.ObjectManager", member="GetManagedObjects"))
                if reply.message_type == MessageType.ERROR:
                    raise RuntimeError("BlueZ device access is unavailable.")
                devices, connected = [], set()
                for interfaces in reply.body[0].values():
                    props = interfaces.get("org.bluez.Device1", {})
                    if not props or not props.get("Paired") or not props["Paired"].value:
                        continue
                    address = props["Address"].value.upper()
                    name = props.get("Alias") or props.get("Name")
                    devices.append((address, name.value if name else address))
                    if props.get("Connected") and props["Connected"].value:
                        connected.add(address)
                return devices, connected, ""
            finally:
                bus.disconnect()

        def run():
            try:
                result = asyncio.run(asyncio.wait_for(scan(), 5))
            except Exception as error:
                result = [], set(), str(error)
            try:
                self.bus_result.emit(result)
            except RuntimeError:
                pass
        threading.Thread(target=run, daemon=True).start()

    def deliver_bus_devices(self, result):
        self.bus_busy = False
        if self.closed:
            return
        devices, self.connected, error = result
        self.devices.emit(sorted(devices, key=lambda item: (not self.matches(item[1]), item[1].lower())))
        if error:
            self.message.emit("Bluetooth device listing unavailable: " + error, True)

    @staticmethod
    def matches(name):
        name = name.lower()
        return any(part in name for part in ("nothing", "cmf", "ear (", "headphone ("))

    def close(self):
        self.closed = True
        if self.process:
            self.process.kill()
            self.process.waitForFinished(100)
