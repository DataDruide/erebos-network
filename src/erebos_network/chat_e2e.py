"""Ende-zu-Ende-Verschluesselung fuer Chat-Partner.

Nutzt X25519 + ML-KEM-1024 (hybrid, quantensicher) fuer den
Schluesselaustausch und ChaCha20-Poly1305 fuer die Nachrichten.

Der Hidden Service speichert nur Public Keys + Ciphertext.
Nur die Chat-Partner koennen Nachrichten entschluesseln.

Protokoll (Initiator/Responder):

1. Initiator generiert X25519 + ML-KEM-Keypair
   -> sendet x25519_pub + mlkem_pub an Server
2. Responder generiert X25519 + ML-KEM-Keypair, encapsuliert mit
   Initiator-mlkem_pub
   -> sendet x25519_pub + mlkem_pub + mlkem_ct an Server
3. Initiator decapsuliert mlkem_ct, leitet Shared Secret ab
4. Beide leiten ChaCha20-Key ab (HKDF ueber x25519_shared || mlkem_shared)

MITM-Schutz: Beide berechnen SHA256(shared_key)[:16] als Fingerprint
(4 Bloecke). Nutzer vergleichen ihn ausserhalb des Kanals (Telefon,
persoenlich). Stimmt er ueberein, ist der Kanal frei von MITM.
"""

import hashlib
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from .crypto.pq_kem import PostQuantumKEM
from .crypto.hybrid_kem import derive_hybrid_key


E2E_CHAT_INFO = b"erebos-chat-e2e-v1"
NONCE_LEN = 12
X25519_PUB_LEN = 32
MLKEM_PUB_LEN = 1568
MLKEM_CT_LEN = 1568


@dataclass
class E2EPayload:
    """Was ein Client an den Server sendet (Key-Exchange)."""

    role: str                # 'initiator' | 'responder'
    x25519_pub: bytes        # 32 B
    mlkem_pub: bytes         # 1568 B
    mlkem_ct: bytes = b""    # 1568 B (nur beim Responder)


class E2ESession:
    """E2E-Session zwischen zwei Chat-Partnern.

    Erzeugt ein eigenes X25519 + ML-KEM-Keypair. Nach dem
    Key-Exchange (finalize_initiator oder finalize_responder)
    kann verschluesselt werden.
    """

    def __init__(self, role: str):
        if role not in ("initiator", "responder"):
            raise ValueError(f"Unbekannte Rolle: {role} (erwartet: initiator|responder)")
        self.role = role

        # X25519-Keypair
        self._x_priv = X25519PrivateKey.generate()
        self.x25519_pub = self._x_priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        # ML-KEM-Keypair
        self._kem = PostQuantumKEM()
        kp = self._kem.generate_keypair()
        self.mlkem_pub = kp.public_key
        self._mlkem_priv = kp.private_key

        # Shared Secret (nach Key-Exchange gesetzt)
        self._shared_key: bytes | None = None
        self._fingerprint: str | None = None

    # ------------------------------------------------------------------
    # Key-Exchange: Initiator -> Server -> Responder -> Server -> Initiator
    # ------------------------------------------------------------------

    def initiator_payload(self) -> E2EPayload:
        """Initiator: sendet seinen Public Key an den Server."""
        if self.role != "initiator":
            raise RuntimeError("initiator_payload nur als Initiator")
        return E2EPayload(
            role="initiator",
            x25519_pub=self.x25519_pub,
            mlkem_pub=self.mlkem_pub,
        )

    def responder_payload(
        self,
        initiator_x25519_pub: bytes,
        initiator_mlkem_pub: bytes,
    ) -> E2EPayload:
        """Responder: encapsuliert mit Initiator-Pubkey, sendet mlkem_ct + eigenen Pubkey."""
        if self.role != "responder":
            raise RuntimeError("responder_payload nur als Responder")
        if len(initiator_x25519_pub) != X25519_PUB_LEN:
            raise ValueError(f"initiator_x25519_pub: {len(initiator_x25519_pub)} statt {X25519_PUB_LEN}")
        if len(initiator_mlkem_pub) != MLKEM_PUB_LEN:
            raise ValueError(f"initiator_mlkem_pub: {len(initiator_mlkem_pub)} statt {MLKEM_PUB_LEN}")

        # ML-KEM: encapsulate mit Initiator-Pubkey
        mlkem_ct, mlkem_shared = self._kem.encapsulate(initiator_mlkem_pub)

        # X25519: Responder-Priv × Initiator-Pub
        initiator_x = X25519PublicKey.from_public_bytes(initiator_x25519_pub)
        x_shared = self._x_priv.exchange(initiator_x)

        # Shared Secret ableiten
        self._shared_key = derive_hybrid_key(x_shared, mlkem_shared, info=E2E_CHAT_INFO)
        self._fingerprint = _fingerprint(self._shared_key)

        return E2EPayload(
            role="responder",
            x25519_pub=self.x25519_pub,
            mlkem_pub=self.mlkem_pub,
            mlkem_ct=mlkem_ct,
        )

    def finalize_initiator(
        self,
        responder_x25519_pub: bytes,
        responder_mlkem_ct: bytes,
    ) -> None:
        """Initiator: decapsuliert mlkem_ct, leitet Shared Secret ab."""
        if self.role != "initiator":
            raise RuntimeError("finalize_initiator nur als Initiator")
        if len(responder_x25519_pub) != X25519_PUB_LEN:
            raise ValueError(f"responder_x25519_pub: {len(responder_x25519_pub)} statt {X25519_PUB_LEN}")
        if len(responder_mlkem_ct) != MLKEM_CT_LEN:
            raise ValueError(f"responder_mlkem_ct: {len(responder_mlkem_ct)} statt {MLKEM_CT_LEN}")

        # ML-KEM: decapsulate
        mlkem_shared = self._kem.decapsulate(responder_mlkem_ct, self._mlkem_priv)

        # X25519: Initiator-Priv × Responder-Pub
        responder_x = X25519PublicKey.from_public_bytes(responder_x25519_pub)
        x_shared = self._x_priv.exchange(responder_x)

        self._shared_key = derive_hybrid_key(x_shared, mlkem_shared, info=E2E_CHAT_INFO)
        self._fingerprint = _fingerprint(self._shared_key)

    # ------------------------------------------------------------------
    # Verschluesselung
    # ------------------------------------------------------------------

    def _require_key(self) -> bytes:
        if self._shared_key is None:
            raise RuntimeError(
                "Key-Exchange nicht abgeschlossen (finalize_initiator / "
                "responder_payload aufrufen)"
            )
        return self._shared_key

    def encrypt(self, plaintext: bytes) -> tuple[bytes, bytes]:
        """Gibt (nonce, ciphertext) zurueck."""
        key = self._require_key()
        nonce = os.urandom(NONCE_LEN)
        ct = ChaCha20Poly1305(key).encrypt(nonce, plaintext, None)
        return nonce, ct

    def decrypt(self, nonce: bytes, ciphertext: bytes) -> bytes:
        key = self._require_key()
        return ChaCha20Poly1305(key).decrypt(nonce, ciphertext, None)

    # ------------------------------------------------------------------
    # Metadaten
    # ------------------------------------------------------------------

    @property
    def fingerprint(self) -> str:
        """4 Bloecke (16 Hex) aus SHA256(shared_key)."""
        if self._fingerprint is None:
            raise RuntimeError("Key-Exchange nicht abgeschlossen")
        return self._fingerprint

    @property
    def is_ready(self) -> bool:
        return self._shared_key is not None


    # ------------------------------------------------------------------
    # Persistenz (optional): Session in JSON-Datei speichern/laden
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Speichert die Session in eine JSON-Datei (chmod 600)."""
        import json
        import os
        from pathlib import Path as _P

        data = {
            "version": 1,
            "role": self.role,
            "x25519_priv": self._x_priv.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption(),
            ).hex(),
            "x25519_pub": self.x25519_pub.hex(),
            "mlkem_priv": self._mlkem_priv.hex(),
            "mlkem_pub": self.mlkem_pub.hex(),
        }
        p = _P(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2))
        os.chmod(p, 0o600)

    @classmethod
    def load(cls, path: str) -> "E2ESession":
        """Laedt eine Session aus einer JSON-Datei."""
        import json
        from pathlib import Path as _P

        data = json.loads(_P(path).read_text())
        if data.get("version") != 1:
            raise ValueError(f"Unbekannte Session-Version: {data.get('version')}")

        # Erzeuge Session ohne neuen Key zu generieren
        session = cls.__new__(cls)
        session.role = data["role"]
        session.x25519_pub = bytes.fromhex(data["x25519_pub"])
        x_priv_bytes = bytes.fromhex(data["x25519_priv"])
        session._x_priv = X25519PrivateKey.from_private_bytes(x_priv_bytes)
        session._kem = PostQuantumKEM()
        session.mlkem_pub = bytes.fromhex(data["mlkem_pub"])
        session._mlkem_priv = bytes.fromhex(data["mlkem_priv"])
        session._shared_key = None
        session._fingerprint = None
        return session


def _fingerprint(key: bytes) -> str:
    """SHA256(key) -> 4 Bloecke, z.B. 'a1b2-c3d4-e5f6-7890'."""
    h = hashlib.sha256(key).hexdigest()[:16]
    return "-".join(h[i:i+4] for i in range(0, 16, 4))


# ---------------------------------------------------------------------------
# DB-Helfer (werden von landing_pages.py + chat.py genutzt)
# ---------------------------------------------------------------------------

def store_key(
    room_id: str,
    cookie: str,
    role: str,
    payload: E2EPayload,
) -> None:
    """Speichert Public Keys in chat_e2e_keys."""
    from .forum_db import get_db
    import time

    conn = get_db()
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO chat_e2e_keys "
            "(room_id, cookie, role, x25519_pub, mlkem_pub, mlkem_ct, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                room_id,
                cookie,
                role,
                payload.x25519_pub,
                payload.mlkem_pub,
                payload.mlkem_ct or None,
                time.time(),
            ),
        )


def get_key(room_id: str, cookie: str) -> dict | None:
    """Holt Public Keys aus chat_e2e_keys."""
    from .forum_db import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT role, x25519_pub, mlkem_pub, mlkem_ct FROM chat_e2e_keys "
        "WHERE room_id = ? AND cookie = ?",
        (room_id, cookie),
    ).fetchone()
    if not row:
        return None
    return {
        "role": row[0],
        "x25519_pub": bytes(row[1]),
        "mlkem_pub": bytes(row[2]),
        "mlkem_ct": bytes(row[3]) if row[3] else b"",
    }


def get_partner_key(room_id: str, my_cookie: str, my_role: str) -> dict | None:
    """Holt den Key des Partners (entgegengesetzte Rolle)."""
    expected_role = "responder" if my_role == "initiator" else "initiator"
    from .forum_db import get_db
    conn = get_db()
    row = conn.execute(
        "SELECT cookie, role, x25519_pub, mlkem_pub, mlkem_ct FROM chat_e2e_keys "
        "WHERE room_id = ? AND cookie != ? AND role = ? LIMIT 1",
        (room_id, my_cookie, expected_role),
    ).fetchone()
    if not row:
        return None
    return {
        "cookie": row[0],
        "role": row[1],
        "x25519_pub": bytes(row[2]),
        "mlkem_pub": bytes(row[3]),
        "mlkem_ct": bytes(row[4]) if row[4] else b"",
    }


def store_encrypted_message(
    room_id: str,
    cookie: str,
    nonce: bytes,
    ciphertext: bytes,
) -> int:
    """Speichert Ciphertext in chat_e2e_messages. Gibt message-id zurueck."""
    from .forum_db import get_db
    import time

    conn = get_db()
    with conn:
        cur = conn.execute(
            "INSERT INTO chat_e2e_messages "
            "(room_id, author_cookie, nonce, ciphertext, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (room_id, cookie, nonce, ciphertext, time.time()),
        )
        return cur.lastrowid


def get_encrypted_messages(room_id: str, since: float = 0.0) -> list[dict]:
    """Holt Ciphertexte aus chat_e2e_messages."""
    from .forum_db import get_db
    conn = get_db()
    rows = conn.execute(
        "SELECT id, author_cookie, nonce, ciphertext, created_at "
        "FROM chat_e2e_messages WHERE room_id = ? AND created_at > ? "
        "ORDER BY created_at ASC",
        (room_id, since),
    ).fetchall()
    return [
        {
            "id": r[0],
            "from": r[1],
            "nonce": bytes(r[2]),
            "ciphertext": bytes(r[3]),
            "ts": r[4],
        }
        for r in rows
    ]
