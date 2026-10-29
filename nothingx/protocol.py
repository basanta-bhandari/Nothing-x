




from dataclasses import dataclass
import struct

HEADER = struct.Struct("<BHHHB")
ANC = {"High": 1, "Mid": 2, "Low": 3, "Adaptive": 4, "Off": 5, "Transparency": 7}
EQ = {"Dirac Opteo": 0, "Rock": 1, "Electronic": 2, "Pop": 3,
      "Enhance vocals": 4, "Classical": 5}


def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def encode(command: int, payload: bytes = b"", sequence: int = 1,
           control: int = 0x0160) -> bytes:
    if len(payload) > 4096:
        raise ValueError("Payload too large")
    body = HEADER.pack(0x55, control, command, len(payload), sequence) + payload
    return body + struct.pack("<H", crc16(body)) if control & 0x20 else body


@dataclass(frozen=True)
class Frame:
    command: int
    payload: bytes
    sequence: int


class Decoder:

    def __init__(self):
        self.buffer = bytearray()
        self.rejected = 0

    def feed(self, data: bytes) -> list[Frame]:
        self.buffer.extend(data)
        frames = []
        while self.buffer:
            if self.buffer[0] != 0x55:
                del self.buffer[0]
                continue
            if len(self.buffer) < HEADER.size:
                break
            _, control, command, length, sequence = HEADER.unpack_from(self.buffer)
            if length > 4096 or control & 0xFF00 not in (0, 0x0100):
                self.rejected += 1
                del self.buffer[0]
                continue
            end = HEADER.size + length
            total = end + (2 if control & 0x20 else 0)
            if len(self.buffer) < total:
                break
            if control & 0x20 and crc16(self.buffer[:end]) != int.from_bytes(self.buffer[end:total], "little"):
                self.rejected += 1
                del self.buffer[0]
                continue
            frames.append(Frame(command | 0x8000, bytes(self.buffer[8:end]), sequence))
            del self.buffer[:total]
        return frames


def _pairs(payload: bytes):
    if not payload or len(payload) < 1 + 2 * payload[0]:
        return []
    return [(payload[i], payload[i + 1]) for i in range(1, 1 + 2 * payload[0], 2)]


def parse(frame: Frame) -> dict:

    cmd, p = frame.command, frame.payload
    if cmd in (0xC007, 0xE001):
        battery = {}
        for key, value in _pairs(p):
            name = {2: "left", 3: "right", 4: "case", 6: "headphone"}.get(key)
            level = value & 0x7F
            if name and level <= 100:
                battery[name] = {"level": level, "charging": bool(value & 0x80)}
        return {"battery": battery} if battery else {}
    if cmd in (0xC01E, 0xE003):
        entries = {p[i]: p[i + 1] for i in range(0, len(p) - 2, 3)}
        mode = entries.get(1)
        if mode in ANC.values():
            if mode in (1, 2, 3, 4) and entries.get(2) in (1, 2, 3, 4):
                mode = entries[2]
            return {"anc": next(k for k, v in ANC.items() if v == mode)}
    if cmd == 0xC050 and p:
        value = p[1] if len(p) >= 2 else p[0]
        if value in EQ.values():
            return {"eq": next(k for k, v in EQ.items() if v == value)}
        return {"eq": f"Device preset {value}"}
    if cmd == 0xC00E:
        for key, value in _pairs(p):
            if key == 1 and value in (0, 1):
                return {"in_ear": bool(value)}
    if cmd == 0xC041 and p and p[0] in (1, 2):
        return {"low_latency": p[0] == 1}
    if cmd == 0xC04F and p and p[0] in (0, 1):
        return {"spatial": bool(p[0])}
    if cmd == 0xC04E and len(p) >= 2 and p[0] in (0, 1) and p[1] <= 10:
        return {"bass": (bool(p[0]), p[1] / 2)}
    if cmd == 0xC029 and p and p[0] in (0, 1, 2):
        return {"codec": p[0]}
    if cmd == 0xC027 and p and p[0] in (0, 1):
        return {"dual": bool(p[0])}
    if cmd == 0xC042 and p:
        return {"firmware": p.decode("utf-8", "replace").strip("\x00\r\n ")}
    if cmd == 0xC01C and p:

        if p in (b"\x72\xb1", b"\x87\xb1"):
            return {"model": {b"\x72\xb1": "B172", b"\x87\xb1": "B187"}[p]}
        text = p.decode("ascii", "ignore").upper()
        for model in ("B172", "B187"):
            if model in text:
                return {"model": model}
        return {"model": text.strip("\x00\r\n ") or p.hex()}
    return {}


READS = {"model": (0xC01C, b""), "battery": (0xC007, b""),
         "anc": (0xC01E, b"\x03"), "eq": (0xC050, b""),
         "in_ear": (0xC00E, b""), "low_latency": (0xC041, b""),
         "spatial": (0xC04F, b""), "bass": (0xC04E, b""),
         "dual": (0xC027, b""), "codec": (0xC029, b""),
         "firmware": (0xC042, b"")}


def write_command(key: str, value) -> tuple[int, bytes]:
    if key == "anc" and value in ANC:
        return 0xF00F, bytes([1, ANC[value], 0])
    if key == "eq" and value in EQ:
        return 0xF01D, bytes([EQ[value], 0])
    if key in ("spatial", "in_ear", "low_latency", "dual") and type(value) is bool:
        return {"spatial": (0xF052, bytes([value, 0])),
                "in_ear": (0xF004, bytes([1, 1, value])),
                "low_latency": (0xF040, bytes([1 if value else 2, 0])),
                "dual": (0xF01A, bytes([value]))}[key]
    if key == "bass" and isinstance(value, tuple) and len(value) == 2:
        enabled, level = value
        if type(enabled) is bool and isinstance(level, (int, float)) and 0 <= level <= 5 and level * 2 == int(level * 2):
            return 0xF051, bytes([enabled, round(level * 2)])
    if key == "codec" and type(value) is int and value in (0, 2):
        return 0xF01C, bytes([value])
    if key == "find" and value in ((2, True), (2, False), (3, True), (3, False)):
        return 0xF002, bytes(value)
    raise ValueError(f"Invalid value for {key}: {value!r}")
