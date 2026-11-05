import errno
import os
import socket

from PySide6.QtCore import QObject, QSocketNotifier, QTimer, Signal


class LinuxBluetoothSocket(QObject):
    connected = Signal()
    readyRead = Signal()
    errorOccurred = Signal(int)
    disconnected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.socket = None
        self.read_notifier = None
        self.write_notifier = None
        self.connecting = False
        self.input = bytearray()
        self.output = bytearray()
        self.error = ""

    def connectToService(self, address, port, mode=None):
        self.abort()
        try:
            self.socket = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            self.socket.setblocking(False)
            address = address.toString() if hasattr(address, "toString") else str(address)
            result = self.socket.connect_ex((address, port))
            self.connecting = True
            self.read_notifier = QSocketNotifier(self.socket.fileno(), QSocketNotifier.Type.Read, self)
            self.read_notifier.setEnabled(False)
            self.read_notifier.activated.connect(self.receive)
            self.write_notifier = QSocketNotifier(self.socket.fileno(), QSocketNotifier.Type.Write, self)
            self.write_notifier.activated.connect(self.writable)
            if result == 0:
                QTimer.singleShot(0, self.writable)
            elif result not in (errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY):
                self.write_notifier.setEnabled(False)
                QTimer.singleShot(0, lambda code=result: self.fail(code))
        except OSError as error:
            QTimer.singleShot(0, lambda code=error.errno or errno.EIO: self.fail(code))

    def writable(self, *_):
        if self.socket is None:
            return
        if self.connecting:
            try:
                error = self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            except OSError as failure:
                self.fail(failure.errno or errno.EIO)
                return
            if error:
                self.fail(error)
                return
            self.connecting = False
            self.read_notifier.setEnabled(True)
            self.write_notifier.setEnabled(False)
            self.connected.emit()
        self.flush()

    def write(self, data):
        if self.socket is None or self.connecting:
            return -1
        data = bytes(data)
        self.output.extend(data)
        self.flush()
        return len(data) if self.socket is not None else -1

    def flush(self):
        if self.socket is None or self.connecting:
            return
        try:
            while self.output:
                try:
                    sent = self.socket.send(self.output)
                except InterruptedError:
                    continue
                if not sent:
                    self.fail(errno.EPIPE)
                    return
                del self.output[:sent]
        except BlockingIOError:
            pass
        except OSError as error:
            self.fail(error.errno or errno.EIO)
            return
        if self.write_notifier is not None:
            self.write_notifier.setEnabled(bool(self.output))

    def receive(self, *_):
        if self.socket is None:
            return
        try:
            data = self.socket.recv(65536)
        except (BlockingIOError, InterruptedError):
            return
        except OSError as error:
            self.fail(error.errno or errno.EIO)
            return
        if not data:
            self.abort()
            self.disconnected.emit()
            return
        self.input.extend(data)
        self.readyRead.emit()

    def readAll(self):
        data = bytes(self.input)
        self.input.clear()
        return data

    def errorString(self):
        return self.error

    def fail(self, code):
        self.error = os.strerror(code)
        self.abort()
        QTimer.singleShot(0, lambda: self.errorOccurred.emit(code))

    def disconnectFromService(self):
        self.flush()
        self.abort()

    def abort(self):
        for name in ("read_notifier", "write_notifier"):
            notifier = getattr(self, name)
            if notifier is not None:
                notifier.setEnabled(False)
                notifier.deleteLater()
                setattr(self, name, None)
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        self.connecting = False
        self.input.clear()
        self.output.clear()
