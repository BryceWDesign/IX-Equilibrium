"""Optional authenticated UDP sensor bridge, using Python's standard library.

No encryption, discovery, time synchronization or guaranteed delivery. The host
must supply a trusted clock, independent producer keys and explicit scopes.
"""
import socket

from .authority import authenticate, sign
from .codec import canonical, loads
from .errors import BoundaryError, EquilibriumError

MAX_DATAGRAM = 8192


class SensorBridge:
    def __init__(self, *, session: str, source_sha256: str, producers: dict,
                 address: tuple[str, int] = ("127.0.0.1", 0)):
        if not session or not producers:
            raise BoundaryError("bridge needs session and explicitly scoped producers")
        self.session, self.source = session, source_sha256
        self.producers = {}
        for principal, config in producers.items():
            if set(config) != {"key", "channels"} or len(config["key"]) < 32 or not config["channels"]:
                raise BoundaryError("producer requires key and channel scope")
            self.producers[principal] = (bytes(config["key"]), frozenset(config["channels"]))
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(address)

    @property
    def address(self):
        return self.socket.getsockname()

    def receive(self, runtime, *, now_ms: int, timeout: float = 1.0) -> dict:
        if runtime.session != self.session or runtime.checked.source_sha256 != self.source:
            raise BoundaryError("bridge/runtime session or source mismatch")
        self.socket.settimeout(timeout)
        try:
            raw, _ = self.socket.recvfrom(MAX_DATAGRAM + 1)
        except TimeoutError as exc:
            raise BoundaryError("sensor transport timeout") from exc
        if len(raw) > MAX_DATAGRAM:
            raise BoundaryError("sensor datagram exceeds 8192 bytes")
        try:
            packet = loads(raw.decode("utf-8"))
            if not isinstance(packet, dict) or set(packet) != {"producer", "token"} or packet["producer"] not in self.producers:
                raise BoundaryError("unknown producer or malformed packet")
            key, scope = self.producers[packet["producer"]]
            payload = authenticate(packet["token"], key)
            if (not isinstance(payload, dict) or set(payload) != {"kind", "session", "source", "sample"}
                or payload["kind"] != "sensor/1" or payload["session"] != self.session or payload["source"] != self.source
                or not isinstance(payload["sample"], dict) or payload["sample"].get("channel") not in scope):
                raise BoundaryError("sensor packet binding or scope mismatch")
            runtime.ingest(payload["sample"], now_ms)
            return {"producer": packet["producer"], "channel": payload["sample"]["channel"], "accepted": True}
        except (UnicodeError, KeyError, TypeError, EquilibriumError) as exc:
            if isinstance(exc, BoundaryError):
                raise
            raise BoundaryError("sensor packet rejected") from exc

    def close(self):
        self.socket.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def send_sample(address: tuple[str, int], *, producer: str, key: bytes,
                session: str, source_sha256: str, sample: dict) -> None:
    token = sign({"kind": "sensor/1", "session": session, "source": source_sha256, "sample": sample}, key)
    raw = canonical({"producer": producer, "token": token}).encode("utf-8")
    if len(raw) > MAX_DATAGRAM:
        raise BoundaryError("sensor datagram exceeds 8192 bytes")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
        sender.sendto(raw, address)
