import socket
import unittest

from equilibrium.errors import EquilibriumError
from equilibrium.transport import SensorBridge, send_sample
from tests.support import fixture, sample


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.rt, _, _, _, _ = fixture()
        self.key = b"s" * 32
        self.bridge = SensorBridge(session=self.rt.session, source_sha256=self.rt.checked.source_sha256,
                                   producers={"force-sensor": {"key": self.key, "channels": ["load"]}})
        self.addCleanup(self.bridge.close)

    def send(self, **changes):
        args = dict(producer="force-sensor", key=self.key, session=self.rt.session,
                    source_sha256=self.rt.checked.source_sha256, sample=sample("load", "1", "N"))
        args.update(changes)
        send_sample(self.bridge.address, **args)

    def test_real_loopback_authenticated_sample(self):
        self.send()
        self.assertTrue(self.bridge.receive(self.rt, now_ms=0)["accepted"])
        self.assertEqual(self.rt.sensors.snapshot(0)[0]["load"].value, 1)

    def test_wrong_key_rejected(self):
        self.send(key=b"x" * 32)
        with self.assertRaises(EquilibriumError):
            self.bridge.receive(self.rt, now_ms=0)
        self.assertNotIn("load", self.rt.sensors.readings)

    def test_producer_scope_escape(self):
        self.send(sample=sample("vision", "1", "m"))
        with self.assertRaises(EquilibriumError):
            self.bridge.receive(self.rt, now_ms=0)
        self.assertNotIn("vision", self.rt.sensors.readings)

    def test_unknown_producer(self):
        self.send(producer="other")
        with self.assertRaises(EquilibriumError):
            self.bridge.receive(self.rt, now_ms=0)

    def test_wrong_session(self):
        self.send(session="other")
        with self.assertRaises(EquilibriumError):
            self.bridge.receive(self.rt, now_ms=0)

    def test_wrong_source(self):
        self.send(source_sha256="f" * 64)
        with self.assertRaises(EquilibriumError):
            self.bridge.receive(self.rt, now_ms=0)

    def test_replayed_datagram_rejected(self):
        self.send()
        self.bridge.receive(self.rt, now_ms=0)
        self.send()
        with self.assertRaises(EquilibriumError):
            self.bridge.receive(self.rt, now_ms=0)

    def test_datagram_size_limit(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(b"x" * 8193, self.bridge.address)
        with self.assertRaises(EquilibriumError):
            self.bridge.receive(self.rt, now_ms=0)

    def test_timeout(self):
        with self.assertRaises(EquilibriumError):
            self.bridge.receive(self.rt, now_ms=0, timeout=0.01)

    def test_malformed_utf8_packet(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(b"\xff", self.bridge.address)
        with self.assertRaises(EquilibriumError):
            self.bridge.receive(self.rt, now_ms=0)


if __name__ == "__main__":
    unittest.main()
