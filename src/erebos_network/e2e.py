"""End-to-End Modus (Forschungsprototyp).

WICHTIG: Dies ist ein symmetrischer Prototyp.
  - shared_secret = secrets.token_bytes(32) (kein KEM-Handshake!)
  - kein Schluesselaustausch zwischen Peers
  - beide Seiten teilen sich das Secret im gleichen Prozess

Fuer echte E2E-Verschluesselung zwischen Peers siehe:
  - auth_handshake.py (authentifizierter Hybrid-Handshake)
  - tunnel.py (verschluesselter Transport)

Krypto:
  - ChaCha20-Poly1305 AEAD (RFC 8439)
  - shared_secret wird per HKDF abgeleitet (RFC 5869)
"""

import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)


class E2EState(Enum):
    """Zustand einer E2E-Verbindung."""

    INITIATED = "initiated"
    HANDSHAKE = "handshake"
    ESTABLISHED = "established"
    CLOSED = "closed"


@dataclass
class E2ESession:
    """Eine End-to-End Session."""

    session_id: str
    initiator_id: str
    responder_id: str
    shared_secret: bytes
    state: E2EState = E2EState.INITIATED
    created_at: float = field(default_factory=time.time)
    messages_sent: int = 0
    messages_received: int = 0

    @property
    def is_established(self) -> bool:
        return self.state == E2EState.ESTABLISHED

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.shared_secret).hexdigest()[:16]


class EndToEnd:
    """End-to-End Modus.

    Beide Peers sind Erebos-Nodes. Kein Exit-Gateway.
    """

    def __init__(self):
        self._sessions: dict[str, E2ESession] = {}
        self.stats = {
            "sessions_created": 0,
            "sessions_established": 0,
            "sessions_closed": 0,
            "messages_sent": 0,
        }

    def create_session(
        self,
        initiator_id: str,
        responder_id: str,
    ) -> E2ESession:
        """Erstellt eine E2E-Session."""
        session_id = hashlib.sha256(
            f"{initiator_id}:{responder_id}:{time.time()}".encode()
        ).hexdigest()[:16]

        shared_secret = secrets.token_bytes(32)

        session = E2ESession(
            session_id=session_id,
            initiator_id=initiator_id,
            responder_id=responder_id,
            shared_secret=shared_secret,
        )
        self._sessions[session_id] = session
        self.stats["sessions_created"] += 1

        logger.info(
            f"E2E-Session erstellt: {session_id} "
            f"({initiator_id[:8]} -> {responder_id[:8]})"
        )
        return session

    def establish(self, session_id: str) -> bool:
        """Markiert Session als etabliert."""
        session = self._sessions.get(session_id)
        if not session:
            return False
        if session.state != E2EState.INITIATED:
            return False
        session.state = E2EState.ESTABLISHED
        self.stats["sessions_established"] += 1
        return True

    def send(
        self,
        session_id: str,
        payload: bytes,
    ) -> bytes:
        """Verschluesselt eine Nachricht (E2E)."""
        session = self._sessions.get(session_id)
        if not session or not session.is_established:
            raise ValueError("Session nicht etabliert")

        # XOR mit SHA-256-Keystream (Prototyp)
        encrypted = self._aead_encrypt(payload, session.shared_secret)
        session.messages_sent += 1
        self.stats["messages_sent"] += 1
        return encrypted

    def receive(self, session_id: str, ciphertext: bytes) -> bytes:
        """Entschluesselt eine Nachricht (E2E)."""
        session = self._sessions.get(session_id)
        if not session or not session.is_established:
            raise ValueError("Session nicht etabliert")

        decrypted = self._aead_decrypt(ciphertext, session.shared_secret)
        session.messages_received += 1
        return decrypted

    def close(self, session_id: str) -> bool:
        """Schliesst eine Session."""
        session = self._sessions.get(session_id)
        if not session:
            return False
        session.state = E2EState.CLOSED
        self.stats["sessions_closed"] += 1
        return True

    @staticmethod
    def _aead_key_from_secret(shared_secret: bytes) -> bytes:
        """HKDF-SHA256: leitet einen 32-Byte AEAD-Key ab (RFC 5869)."""
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"erebos-e2e-aead-v1",
        ).derive(shared_secret)

    @classmethod
    def _aead_encrypt(cls, data: bytes, shared_secret: bytes) -> bytes:
        """ChaCha20-Poly1305 AEAD-Verschluesselung (RFC 8439).

        Liefert (nonce(12) || ciphertext || tag(16)).
        """
        key = cls._aead_key_from_secret(shared_secret)
        nonce = os.urandom(12)
        ct = ChaCha20Poly1305(key).encrypt(nonce, data, None)
        return nonce + ct

    @classmethod
    def _aead_decrypt(cls, data: bytes, shared_secret: bytes) -> bytes:
        """ChaCha20-Poly1305 AEAD-Entschluesselung."""
        if len(data) < 12 + 16:
            raise ValueError(f"Zu kurz fuer AEAD: {len(data)} Byte")
        key = cls._aead_key_from_secret(shared_secret)
        nonce, ct = data[:12], data[12:]
        return ChaCha20Poly1305(key).decrypt(nonce, ct, None)

    # Backward-Compat: alter Name (war XOR).
    _xor_encrypt = _aead_encrypt

    @property
    def active_sessions(self) -> int:
        return sum(
            1 for s in self._sessions.values()
            if s.is_established
        )

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "active_sessions": self.active_sessions,
            "total_sessions": len(self._sessions),
        }
