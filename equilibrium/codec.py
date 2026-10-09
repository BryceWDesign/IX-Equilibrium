"""Canonical JSON for evidence, authority and checked artifacts."""
import hashlib
import json
from dataclasses import asdict, is_dataclass
from decimal import Decimal
from pathlib import Path

from .errors import EquilibriumError
from .units import fmt


def normalize(value):
    if isinstance(value, Decimal):
        return fmt(value)
    if is_dataclass(value):
        return normalize(asdict(value))
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    return value


def canonical(value) -> str:
    return json.dumps(normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def source_digest(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def loads(text: str):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise EquilibriumError(f"duplicate JSON key {k}")
            out[k] = v
        return out

    def invalid(value):
        raise EquilibriumError(f"nonfinite JSON value {value}")

    if len(text.encode("utf-8")) > 20_000_000:
        raise EquilibriumError("JSON exceeds 20 MB")
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_float=invalid, parse_constant=invalid)
    except (ValueError, RecursionError) as exc:
        raise EquilibriumError("invalid JSON") from exc


def read_json(path: str | Path):
    return loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, value) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(normalize(value), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")

