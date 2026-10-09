"""Verify the release manifest, excluding the self-referential manifest file."""
import hashlib
from pathlib import Path

root = Path(__file__).resolve().parents[1]
count = 0
for line in (root / "MANIFEST.sha256").read_text().splitlines():
    sha, name = line.split("  ", 1)
    path = root / name
    if path.resolve().parent != root.resolve() and root.resolve() not in path.resolve().parents:
        raise SystemExit("Manifest path escapes release")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != sha:
        raise SystemExit(f"Hash mismatch: {name}")
    count += 1
print(f"Verified {count} files")

