"""Host-owned authenticated grants and single-use exact-action approvals.

HMAC authenticates possession of a host key. It is not a personal signature or
an identity provider. Callers own key distribution and principal authentication.
"""
import hashlib
import hmac
import threading
from dataclasses import dataclass

from .codec import canonical, digest
from .errors import BoundaryError


@dataclass(frozen=True)
class Action:
    source_sha256: str
    session: str
    tick: int
    at_ms: int
    state: str
    outputs: dict

    @property
    def sha256(self) -> str:
        return digest(self)


def sign(payload: dict, key: bytes) -> dict:
    if len(key) < 32:
        raise BoundaryError("authority keys require at least 32 bytes")
    mac = hmac.new(key, canonical(payload).encode(), hashlib.sha256).hexdigest()
    return {"payload": payload, "mac": mac}


def authenticate(token, key):
    if not isinstance(token, dict) or set(token) != {"payload", "mac"}:
        raise BoundaryError("malformed authority token")
    expected = sign(token["payload"], key)["mac"]
    if not isinstance(token["mac"], str) or not hmac.compare_digest(token["mac"], expected):
        raise BoundaryError("invalid authority MAC")
    return token["payload"]


class Authority:
    def __init__(self, grant_key: bytes, review_key: bytes):
        if grant_key == review_key or min(len(grant_key), len(review_key)) < 32:
            raise BoundaryError("use distinct grant/review keys of at least 32 bytes")
        self._grant_key, self._review_key = grant_key, review_key
        self._revoked, self._used = set(), set()
        self._lock = threading.RLock()

    def issue_grant(self, *, source_sha256: str, session: str, principal: str,
                    actuators: list[str], not_before_ms: int, expires_ms: int,
                    nonce: str, review_required: bool = True) -> dict:
        if not principal or not session or not nonce or not actuators or len(set(actuators)) != len(actuators):
            raise BoundaryError("grant requires principal, session, nonce and unique actuator scope")
        if type(not_before_ms) is not int or type(expires_ms) is not int or not 0 <= not_before_ms < expires_ms:
            raise BoundaryError("invalid grant validity interval")
        if type(review_required) is not bool:
            raise BoundaryError("review_required must be bool")
        return sign({"kind": "grant/1", "source": source_sha256, "session": session,
                     "principal": principal, "actuators": sorted(actuators),
                     "not_before_ms": not_before_ms, "expires_ms": expires_ms,
                     "nonce": nonce, "review_required": review_required}, self._grant_key)

    def issue_review(self, action: Action, *, reviewer: str, expires_ms: int, nonce: str) -> dict:
        if not reviewer or not nonce or type(expires_ms) is not int or expires_ms <= action.at_ms:
            raise BoundaryError("review requires identity, nonce and future expiration")
        return sign({"kind": "review/1", "action": action.sha256, "session": action.session,
                     "reviewer": reviewer, "expires_ms": expires_ms, "nonce": nonce}, self._review_key)

    def revoke(self, nonce: str) -> None:
        with self._lock:
            self._revoked.add(nonce)

    def check_grant(self, action: Action, grant: dict | None, active: set[str]) -> dict:
        with self._lock:
            try:
                g = authenticate(grant, self._grant_key)
                if set(g) != {"kind", "source", "session", "principal", "actuators", "not_before_ms", "expires_ms", "nonce", "review_required"}:
                    raise BoundaryError("invalid grant schema")
                if (g["kind"] != "grant/1" or g["source"] != action.source_sha256
                    or g["session"] != action.session or g["nonce"] in self._revoked
                    or type(g["not_before_ms"]) is not int or type(g["expires_ms"]) is not int
                    or not g["not_before_ms"] <= action.at_ms < g["expires_ms"]
                    or not isinstance(g["actuators"], list) or not active <= set(g["actuators"])
                    or type(g["review_required"]) is not bool or not isinstance(g["principal"], str)
                    or not g["principal"]):
                    raise BoundaryError("grant scope, revocation or validity failed")
                return g
            except (KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, BoundaryError):
                    raise
                raise BoundaryError("malformed grant fields") from exc

    def authorize(self, action: Action, grant: dict | None, review: dict | None,
                  active: set[str]) -> dict:
        with self._lock:
            try:
                g = self.check_grant(action, grant, active)
                result = {"principal": g["principal"], "grant_nonce": g["nonce"], "reviewer": None}
                if g["review_required"]:
                    r = authenticate(review, self._review_key)
                    if set(r) != {"kind", "action", "session", "reviewer", "expires_ms", "nonce"}:
                        raise BoundaryError("invalid review schema")
                    key = (r["session"], r["nonce"])
                    if (r["kind"] != "review/1" or r["action"] != action.sha256
                        or r["session"] != action.session or type(r["expires_ms"]) is not int
                        or action.at_ms >= r["expires_ms"] or r["nonce"] in self._revoked
                        or key in self._used or not isinstance(r["reviewer"], str) or not r["reviewer"]):
                        raise BoundaryError("review binding, replay, revocation or validity failed")
                    self._used.add(key)  # consumed before dispatch; never reused after failures
                    result["reviewer"] = r["reviewer"]
                return result
            except (KeyError, TypeError, ValueError) as exc:
                if isinstance(exc, BoundaryError):
                    raise
                raise BoundaryError("malformed authority fields") from exc

