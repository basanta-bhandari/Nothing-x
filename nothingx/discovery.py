import re
import sys

from PySide6.QtCore import QObject, QCoreApplication, QProcess, QTimer, QBluetoothPermission, Qt, Signal


class Discovery(QObject):
    devices = Signal(list)
    message = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None
        self.connected = set()

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
        self.permission(self.scan)

    def scan(self, granted):
        if not granted:
            self.message.emit("Allow Bluetooth access for Nothing X in macOS System Settings → Privacy & Security → Bluetooth.", True)
            self.devices.emit([])
            return
        if sys.platform == "darwin":
            self.mac_devices()
            return
        if self.process and self.process.state() != QProcess.ProcessState.NotRunning:
            return
        process = QProcess(self)
        self.process = process
        timer = QTimer(process)
        timer.setSingleShot(True)
        timer.setInterval(5000)
        timer.timeout.connect(process.kill)

        def done(code, *_):
            timer.stop()
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
            if self.process is process:
                self.process = None

        process.finished.connect(done)
        process.errorOccurred.connect(lambda error: self.message.emit("Install bluez-utils to list paired devices.", True) if error == QProcess.ProcessError.FailedToStart else None)
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

    @staticmethod
    def matches(name):
        name = name.lower()
        return any(part in name for part in ("nothing", "cmf", "ear (", "headphone ("))

    def close(self):
        if self.process:
            self.process.kill()
