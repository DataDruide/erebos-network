"""Erebos Key-Generator für Peer-Identitäten."""

import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
from cryptography.hazmat.primitives import serialization

KEYS_DIR = Path(__file__).parent.parent / "erebos_keys"


def _raw_priv(key) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _raw_pub(key) -> bytes:
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def generate_identity(name: str) -> None:
    KEYS_DIR.mkdir(exist_ok=True)

    ed = Ed25519PrivateKey.generate()
    x = X25519PrivateKey.generate()

    ed_bytes = _raw_priv(ed)
    x_bytes = _raw_priv(x)
    x_pub = _raw_pub(x)

    (KEYS_DIR / f"{name}_ed25519").write_bytes(ed_bytes)
    (KEYS_DIR / f"{name}_x25519").write_bytes(x_bytes)
    (KEYS_DIR / f"{name}_x25519.pub").write_bytes(x_pub)

    print(f"[{name}]")
    print(f"  ed25519 (priv): {ed_bytes.hex()}")
    print(f"  x25519  (priv): {x_bytes.hex()}")
    print(f"  x25519  (pub) : {x_pub.hex()}")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_keys.py <name> [<name> ...]")
        print("Beispiel: python scripts/generate_keys.py peer1 peer2")
        sys.exit(1)

    for name in sys.argv[1:]:
        generate_identity(name)
