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
    """Stellt sicher, dass X25519-Keypairs fuer peer1..peer3 existieren.

    Ueberschreibt vorhandene Dateien NICHT — sonst werden bei jedem
    pytest-Lauf die Keys neu generiert, was den Docker-Betrieb
    zerschiessen wuerde (Proxy und Peers haetten unterschiedliche
    Keys -> Onion-Tunnel bricht mit InvalidTag).

    Zum Regenerieren: Dateien loeschen, dann pytest laufen lassen.
    """
    KEYS_DIR.mkdir(exist_ok=True)
    for i in (1, 2, 3):
        priv_path = KEYS_DIR / f"peer{i}_x25519"
        pub_path = KEYS_DIR / f"peer{i}_x25519.pub"
        if priv_path.exists() and pub_path.exists():
            continue  # bestehende Keys behalten
        _write_x25519_pair(KEYS_DIR, f"peer{i}")
    yield

# ============================================================
# Mail-Rotation + Persistenz-Fixtures (Phase 2b + Rotation)
# ============================================================

@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Frische sqlite-DB pro Test, gepatched in forum_db.

    Setzt forum_db.DB_PATH auf eine temporaere Datei und resettet
    die gecachte Connection, damit get_db() neu initialisiert
    (inkl. aller _migrate_*-Funktionen).
    """
    from erebos_network import forum_db

    test_db = tmp_path / "test.db"
    monkeypatch.setattr(forum_db, "DB_PATH", test_db)
    monkeypatch.setattr(forum_db, "_conn", None)

    conn = forum_db.get_db()
    assert conn is not None
    yield test_db

    try:
        conn.close()
    except Exception:
        pass
    monkeypatch.setattr(forum_db, "_conn", None)


@pytest.fixture
def uuid_a():
    return "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


@pytest.fixture
def uuid_b():
    return "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


@pytest.fixture
def fresh_keys_a(temp_db, uuid_a):
    """Erzeugt v1-Keys fuer uuid_a."""
    from erebos_network.forum_db import get_or_create_mail_keys
    return get_or_create_mail_keys(uuid_a)


@pytest.fixture
def fresh_keys_b(temp_db, uuid_b):
    """Erzeugt v1-Keys fuer uuid_b (Empfaenger)."""
    from erebos_network.forum_db import get_or_create_mail_keys
    return get_or_create_mail_keys(uuid_b)


@pytest.fixture
def rotated_keys_a(temp_db, uuid_a, fresh_keys_a):
    """v1 -> v2 Rotation fuer uuid_a. Returnt v2-Keys."""
    from erebos_network.forum_db import rotate_mail_keys
    return rotate_mail_keys(uuid_a)
