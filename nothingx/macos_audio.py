import ctypes as C
import struct

from PySide6.QtCore import QObject, QTimer, Signal


def fourcc(value):
    return int.from_bytes(value.encode("ascii"), "big")


class Address(C.Structure):
    _fields_ = [("selector", C.c_uint32), ("scope", C.c_uint32), ("element", C.c_uint32)]


class CoreAudio:
    def __init__(self):
        self.audio = C.CDLL("/System/Library/Frameworks/CoreAudio.framework/CoreAudio")
        self.foundation = C.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.audio.AudioObjectGetPropertyDataSize.argtypes = [C.c_uint32, C.POINTER(Address), C.c_uint32, C.c_void_p, C.POINTER(C.c_uint32)]
        self.audio.AudioObjectGetPropertyData.argtypes = [C.c_uint32, C.POINTER(Address), C.c_uint32, C.c_void_p, C.POINTER(C.c_uint32), C.c_void_p]
        self.audio.AudioObjectSetPropertyData.argtypes = [C.c_uint32, C.POINTER(Address), C.c_uint32, C.c_void_p, C.c_uint32, C.c_void_p]
        self.audio.AudioObjectHasProperty.argtypes = [C.c_uint32, C.POINTER(Address)]
        self.audio.AudioObjectHasProperty.restype = C.c_bool
        self.audio.AudioObjectIsPropertySettable.argtypes = [C.c_uint32, C.POINTER(Address), C.POINTER(C.c_bool)]
        self.foundation.CFStringGetCString.argtypes = [C.c_void_p, C.c_char_p, C.c_long, C.c_uint32]
        self.foundation.CFStringGetCString.restype = C.c_bool
        self.foundation.CFRelease.argtypes = [C.c_void_p]

    def address(self, selector, scope="glob", element=0):
        return Address(fourcc(selector), fourcc(scope), element)

    def get(self, device, selector, scope="glob", element=0):
        address = self.address(selector, scope, element)
        size = C.c_uint32()
        if self.audio.AudioObjectGetPropertyDataSize(device, C.byref(address), 0, None, C.byref(size)) or size.value > 1048576:
            return None
        data = C.create_string_buffer(size.value)
        if self.audio.AudioObjectGetPropertyData(device, C.byref(address), 0, None, C.byref(size), data):
            return None
        return data.raw[:size.value]

    def scalar(self, device, selector, dtype, scope="glob", element=0, default=None):
        data = self.get(device, selector, scope, element)
        return dtype.from_buffer_copy(data).value if data and len(data) >= C.sizeof(dtype) else default

    def text(self, device, selector):
        value = self.scalar(device, selector, C.c_void_p)
        if not value:
            return ""
        buffer = C.create_string_buffer(2048)
        try:
            return buffer.value.decode(errors="replace") if self.foundation.CFStringGetCString(value, buffer, len(buffer), 0x08000100) else ""
        finally:
            self.foundation.CFRelease(value)

    def writable(self, device, selector, scope="glob", element=0):
        address = self.address(selector, scope, element)
        allowed = C.c_bool()
        return bool(self.audio.AudioObjectHasProperty(device, C.byref(address)) and not self.audio.AudioObjectIsPropertySettable(device, C.byref(address), C.byref(allowed)) and allowed.value)

    def set(self, device, selector, value, scope="glob", element=0):
        if not self.writable(device, selector, scope, element):
            raise ValueError("This device does not expose that audio control to macOS.")
        address = self.address(selector, scope, element)
        status = self.audio.AudioObjectSetPropertyData(device, C.byref(address), 0, None, C.sizeof(value), C.byref(value))
        if status:
            raise ValueError(f"CoreAudio rejected this change ({status}).")

    def devices(self):
        data = self.get(1, "dev#") or b""
        return list(struct.unpack(f"={len(data) // 4}I", data)) if data else []

    def endpoint(self, device, scope):
        streams = self.get(device, "stm#", scope)
        if not streams:
            return None
        name = self.text(device, "lnam") or f"Audio device {device}"
        uid = self.text(device, "uid ")
        master = self.scalar(device, "volm", C.c_float, scope)
        left = self.scalar(device, "volm", C.c_float, scope, 1)
        right = self.scalar(device, "volm", C.c_float, scope, 2)
        channel_control = left is not None and right is not None
        volume = master if master is not None else max(left or 0, right or 0)
        balance = 0
        if channel_control and max(left, right):
            balance = round((right - left) / max(left, right) * 100)
        rate = self.scalar(device, "nsrt", C.c_double, default=0)
        return {"name": str(device), "index": device, "description": name, "uid": uid, "volume": round(volume * 100),
                "mute": bool(self.scalar(device, "mute", C.c_uint32, scope, default=0)), "balance": balance,
                "channels": ["front-left", "front-right"] if channel_control else ["mono"], "codec": "", "sample": f"{rate:g} Hz" if rate else "",
                "volume_control": self.writable(device, "volm", scope) or self.writable(device, "volm", scope, 1),
                "mute_control": self.writable(device, "mute", scope),
                "balance_control": channel_control and self.writable(device, "volm", scope, 1) and self.writable(device, "volm", scope, 2)}

    def volume(self, device, scope, percent, balance=0):
        if self.writable(device, "volm", scope):
            self.set(device, "volm", C.c_float(percent / 100), scope)
        else:
            self.set(device, "volm", C.c_float(percent / 100 * (1 - max(0, balance) / 100)), scope, 1)
            self.set(device, "volm", C.c_float(percent / 100 * (1 + min(0, balance) / 100)), scope, 2)


class MacAudio(QObject):
    event = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.core = CoreAudio()
        self.address = ""
        self.state = {}
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        QTimer.singleShot(0, self.refresh)

    def refresh(self):
        sinks, sources = [], []
        for device in self.core.devices():
            for scope, values in (("outp", sinks), ("inpt", sources)):
                endpoint = self.core.endpoint(device, scope)
                if endpoint:
                    values.append(endpoint)
        matching = [s for s in sinks if self.address.replace(":", "").lower() in s["uid"].replace(":", "").replace("-", "").lower()] if self.address else []
        if not matching:
            matching = [s for s in sinks if any(word in s["description"].lower() for word in ("nothing", "cmf", "ear (", "headphone ("))]
        self.state = {"available": True, "server": "CoreAudio", "card": None, "sink": matching[0] if len(matching) == 1 else None,
                      "sinks": sinks, "sources": sources, "streams": [], "auto_headset": None,
                      "default_sink": str(self.core.scalar(1, "dOut", C.c_uint32, default=0)),
                      "default_source": str(self.core.scalar(1, "dIn ", C.c_uint32, default=0)),
                      "capabilities": {"profiles": False, "balance": True, "streams": False, "microphones": True}}
        self.event.emit({"type": "audio", "state": self.state})

    def request(self, key, value=None, target=None):
        try:
            if key == "address":
                self.address = str(value or "").upper()
            elif key != "refresh":
                self.apply(key, value, target)
            self.refresh()
        except (ValueError, OSError) as error:
            self.event.emit({"type": "message", "text": str(error), "error": True})
        self.event.emit({"type": "audio_completed", "key": key})

    def apply(self, key, value, target):
        sink = self.state.get("sink")
        if key in ("output_volume", "output_mute", "balance", "default_output") and sink:
            device = sink["index"]
            if key == "default_output":
                self.core.set(1, "dOut", C.c_uint32(device))
            elif key == "output_mute" and type(value) is bool:
                self.core.set(device, "mute", C.c_uint32(value), "outp")
            elif key == "output_volume" and type(value) is int and 0 <= value <= 100:
                self.core.volume(device, "outp", value, sink["balance"])
            elif key == "balance" and type(value) is int and -100 <= value <= 100 and sink.get("balance_control"):
                self.core.set(device, "volm", C.c_float(sink["volume"] / 100 * (1 - max(0, value) / 100)), "outp", 1)
                self.core.set(device, "volm", C.c_float(sink["volume"] / 100 * (1 + min(0, value) / 100)), "outp", 2)
            else:
                raise ValueError("Invalid or unavailable output control.")
        elif key in ("default_input", "input_volume", "input_mute"):
            source = next((s for s in self.state["sources"] if s["name"] == target), None)
            if not source:
                raise ValueError("This microphone is no longer available.")
            if key == "default_input":
                self.core.set(1, "dIn ", C.c_uint32(source["index"]))
            elif key == "input_mute" and type(value) is bool:
                self.core.set(source["index"], "mute", C.c_uint32(value), "inpt")
            elif key == "input_volume" and type(value) is int and 0 <= value <= 100:
                self.core.volume(source["index"], "inpt", value)
            else:
                raise ValueError("Invalid microphone setting.")
        else:
            raise ValueError("This control is managed by macOS or is unavailable on this device.")

    def close(self):
        self.timer.stop()
