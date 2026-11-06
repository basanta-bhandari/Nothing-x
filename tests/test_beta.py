import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QCoreApplication, QObject, Signal

from nothingx.core import NativeClient
from nothingx.models import MODELS
from nothingx.service import Service


class AudioStub(QObject):
    event = Signal(dict)
    state = {}

    def close(self):
        pass

    def request(self, *args):
        pass

    def refresh(self):
        pass


class Transport:
    def __init__(self):
        self.packets = []

    def write(self, data):
        self.packets.append(data)
        return len(data)

    def disconnectFromService(self):
        pass

    def deleteLater(self):
        pass


class ServiceChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.audio = patch("nothingx.service.make_audio", lambda parent: AudioStub(parent))
        self.audio.start()
        self.service = Service("rust")
        self.addCleanup(self.audio.stop)
        self.addCleanup(self.service.close)

    def test_disconnected_service_has_no_polling_timer(self):
        self.assertFalse(self.service.timer.isActive())
        self.service.start_demo()
        self.assertFalse(self.service.timer.isActive())

    def test_clicks_preserve_active_request_and_fifo_priority(self):
        service = self.service
        service.transport = Transport()
        completed = []
        service.request("read", key="battery", callback=lambda frame: completed.append(frame))
        active = service.active
        service.request("read", key="firmware")
        service.request("read", key="anc", urgent=True)
        service.request("read", key="eq", urgent=True)
        self.assertIs(service.active, active)
        self.assertEqual(completed, [])
        queued = list(service.requests)
        self.assertEqual([job["urgent"] for job in queued], [True, True, False])
        service.complete({"ack": True})
        self.assertIs(service.active, queued[0])
        self.assertEqual(completed, [{"ack": True}])
        service.complete(None)
        self.assertIs(service.active, queued[1])

    def test_timeout_advances_queue_and_stops_timer(self):
        service = self.service
        service.transport = Transport()
        completed = []
        service.request("read", key="battery", callback=completed.append)
        service.active["deadline"] = time.monotonic() - 1
        service.tick()
        self.assertEqual(completed, [None])
        self.assertIsNone(service.active)
        self.assertFalse(service.timer.isActive())

    def test_locator_stop_is_only_queued_once(self):
        service = self.service
        service.phase = "connected"
        service.ringing[2] = time.monotonic() - 1
        with patch.object(service, "write") as write:
            service.tick()
            service.tick()
        write.assert_called_once_with("find", [2, False])

    def test_reentrant_transport_failure_keeps_replacement(self):
        service = self.service
        replacement = Transport()
        failing = Transport()
        def fail(data):
            service.transport = replacement
            service.active = None
            return -1
        failing.write = fail
        service.transport = failing
        service.request("read", key="battery")
        self.assertIs(service.transport, replacement)

    def test_refresh_is_deduplicated(self):
        service = self.service
        service.start_demo()
        service.demo = False
        service.phase = "connected"
        service.transport = Transport()
        service.refresh()
        count = len(service.requests)
        service.refresh()
        self.assertEqual(len(service.requests), count)
        self.assertLess(count, 12)

    def test_fragmented_response_completes_only_after_full_frame(self):
        service = self.service
        service.transport = Transport()
        completed = []
        service.request("read", key="battery", callback=completed.append)
        packet = bytes(service.engine.call("packet", command=service.active["command"], sequence=service.active["sequence"], payload=[3, 2, 92, 3, 88, 4, 76])["bytes"])
        for byte in packet[:-1]:
            service.feed(bytes([byte]))
        self.assertEqual(completed, [])
        service.feed(packet[-1:])
        self.assertEqual(len(completed), 1)
        self.assertIsNone(service.active)

    def test_queue_is_bounded(self):
        for _ in range(128):
            self.service.request("read", key="battery")
        with self.assertRaises(ValueError):
            self.service.request("read", key="battery")

    def test_parser_recovers_from_noise_bad_crc_and_keeps_partial_tail(self):
        engine = self.service.engine
        command = engine.call("read", key="battery")["command"]
        packet = engine.call("packet", command=command, sequence=7, payload=[1, 2, 92])["bytes"]
        broken = packet.copy()
        broken[-1] ^= 1
        result = engine.call("feed", bytes=[0] * 32000 + broken + packet + packet[:4])
        self.assertEqual(len(result["frames"]), 1)
        self.assertEqual(result["frames"][0]["sequence"], 7)
        result = engine.call("feed", bytes=packet[4:] + packet)
        self.assertEqual(len(result["frames"]), 2)

    def test_closed_engine_rejects_calls(self):
        self.service.close()
        with self.assertRaises(RuntimeError):
            self.service.engine.call("state")
        with self.assertRaises(RuntimeError):
            self.service.request("read", key="battery")

    def test_every_model_demo_and_supported_controls(self):
        service = self.service
        for model in MODELS:
            with self.subTest(model=model):
                service.start_demo(model)
                state = service.state()
                self.assertEqual(state["model"], model)
                for key in ("anc", "eq", "low_latency", "bass", "spatial", "in_ear", "dual", "codec"):
                    if key in state:
                        service.write(key, state[key])
                        self.assertEqual(service.state()[key], state[key])

    def test_reconnect_does_not_replay_device_writes(self):
        client = NativeClient()
        client.starting = True
        events = []
        client.event.connect(events.append)
        client.send({"action": "write", "key": "anc", "value": "Off"})
        client.send({"action": "audio", "key": "output_volume", "value": 100})
        for _ in range(100):
            client.send({"action": "devices"})
        self.assertEqual(client.waiting, [{"action": "devices"}])
        self.assertTrue(any(event["type"] == "completed" for event in events))
        self.assertTrue(any(event["type"] == "audio_completed" for event in events))
        client.stop()


if __name__ == "__main__":
    unittest.main()
