"""Pytest-Fixtures für Erebos-Netzwerk.

Wichtig: Erzeugt ECHTE X25519-Keypairs. Zufällige Bytes wären nicht
mathematisch verknüpft und würden bei ECDH-Tests (onion.py) fehlschlagen.
"""
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey


KEYS_DIR = Path(__file__).parent.parent / "erebos_keys"


def _write_x25519_pair(keys_dir: Path, name: str) -> None:
    """Schreibt ein konsistentes X25519-Keypair.

    Dateinamen passen zu test_onion_basic.py:
      <name>_x25519      -> private (Raw, 32 Byte)
      <name>_x25519.pub  -> public  (Raw, 32 Byte)
    """
    priv = X25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    (keys_dir / f"{name}_x25519").write_bytes(priv_bytes)
    (keys_dir / f"{name}_x25519.pub").write_bytes(pub_bytes)


@pytest.fixture(scope="session", autouse=True)
def generate_test_keys():
    """Erzeugt X25519-Keypairs für peer1..peer3 (session-scoped, autouse).

    Überschreibt vorhandene Dateien IMMER — falls vorherige Läufe
    inkonsistente Zufallsbytes hinterlassen haben.
    """
    KEYS_DIR.mkdir(exist_ok=True)
    for i in (1, 2, 3):
        _write_x25519_pair(KEYS_DIR, f"peer{i}")
    yield
