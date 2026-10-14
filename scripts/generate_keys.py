"""Erebos Key-Generator fuer Peer-Identitaeten.

Erzeugt pro Identitaet:
  <name>_ed25519       32 Byte private (Raw)   Ed25519-Signaturschluessel
  <name>_x25519        32 Byte private (Raw)   X25519-Schluesselaustausch
  <name>_x25519.pub    32 Byte public  (Raw)
  <name>_mlkem        3168 Byte private (Raw)  ML-KEM-1024 (FIPS 203)
  <name>_mlkem.pub    1568 Byte public  (Raw)
"""

import sys
from pathlib import Path

import oqs
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

    # Klassische Schluessel
    ed = Ed25519PrivateKey.generate()
    x = X25519PrivateKey.generate()

    ed_bytes = _raw_priv(ed)
    x_bytes = _raw_priv(x)
    x_pub = _raw_pub(x)

    (KEYS_DIR / f"{name}_ed25519").write_bytes(ed_bytes)
    (KEYS_DIR / f"{name}_x25519").write_bytes(x_bytes)
    (KEYS_DIR / f"{name}_x25519.pub").write_bytes(x_pub)

    # ML-KEM-1024 (FIPS 203)
    with oqs.KeyEncapsulation("ML-KEM-1024") as kem:
        mlkem_pub = kem.generate_keypair()
        mlkem_priv = kem.export_secret_key()

    (KEYS_DIR / f"{name}_mlkem").write_bytes(mlkem_priv)
    (KEYS_DIR / f"{name}_mlkem.pub").write_bytes(mlkem_pub)

    # Ausgabe (nur Laengen, keine privaten Hex-Werte)
    print(f"[{name}]")
    print(f"  ed25519 (priv): {len(ed_bytes):5d} B  {ed_bytes.hex()[:16]}...")
    print(f"  x25519  (priv): {len(x_bytes):5d} B  {x_bytes.hex()[:16]}...")
    print(f"  x25519  (pub) : {len(x_pub):5d} B  {x_pub.hex()[:16]}...")
    print(f"  mlkem   (priv): {len(mlkem_priv):5d} B")
    print(f"  mlkem   (pub) : {len(mlkem_pub):5d} B")
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_keys.py <name> [<name> ...]")
        print("Beispiel: python scripts/generate_keys.py peer1 peer2")
        sys.exit(1)

    for name in sys.argv[1:]:
        generate_identity(name)
