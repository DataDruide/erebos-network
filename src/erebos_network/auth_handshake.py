"""Authentifizierter Hybrid-Handshake fuer Erebos.

Behebt Schwachstellen, die durch formale Verifikation (Tamarin)
gefunden wurden:
- Keine Authentifizierung -> Impersonation
- Keine Key-Bestaetigung -> unbestätigter Session-Key

Basiert auf PQ-IKEv2 (Heid 2019) + Signal-Protokoll-Prinzipien.
"""

import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .crypto.hybrid_kem import (
    HybridKEM,
    HybridKeyPair,
    HybridCiphertext,
    derive_hybrid_key,
)
from .crypto.pq_kem import PostQuantumKEM
from .crypto.pq_sig import PostQuantumSignature, SignatureKeyPair
from .crypto.threefish import ThreefishAEAD

logger = logging.getLogger(__name__)


class HandshakeState(Enum):
    """Zustand des Handshakes."""

    INITIATED = "initiated"
    RESPONDED = "responded"
    CONFIRMED = "confirmed"
    FAILED = "failed"


@dataclass
class HandshakeConfig:
    """Konfiguration fuer den authentifizierten Handshake."""

    use_signatures: bool = True
    use_mac: bool = True
    session_binding: bool = True
    timestamp_check: bool = True
    max_timestamp_skew_seconds: int = 300


@dataclass
class HandshakeMessage:
    """Eine Handshake-Nachricht."""

    sender_id: str
    x25519_pub: bytes
    mlkem_ct: bytes
    signature: bytes = b""
    mac: bytes = b""
    timestamp: float = field(default_factory=time.time)

    def to_bytes(self) -> bytes:
        """Serialisiert die Nachricht."""
        return (
            self.sender_id.encode()
            + b"|"
            + self.x25519_pub
            + b"|"
            + self.mlkem_ct
            + b"|"
            + self.signature
            + b"|"
            + self.mac
            + b"|"
            + str(self.timestamp).encode()
        )

    def signable_bytes(self) -> bytes:
        """Bytes, die signiert werden."""
        return (
            self.sender_id.encode()
            + b"|"
            + self.x25519_pub
            + b"|"
            + self.mlkem_ct
            + b"|"
            + str(self.timestamp).encode()
        )


@dataclass
class AuthenticatedSession:
    """Eine authentifizierte Session."""

    session_id: str
    initiator_id: str
    responder_id: str
    session_key: bytes
    aead: ThreefishAEAD
    state: HandshakeState
    created_at: float = field(default_factory=time.time)
    confirmed_at: Optional[float] = None

    @property
    def is_confirmed(self) -> bool:
        return self.state == HandshakeState.CONFIRMED

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.session_key).hexdigest()[:16]


class AuthenticatedHandshake:
    """Authentifizierter Hybrid-Handshake.

    Schuetzt gegen:
    - Impersonation (SLH-DSA-Signaturen)
    - Replay (Timestamps + MAC)
    - Unknown Key-Share (Session-Bindung)
    """

    def __init__(self, config: Optional[HandshakeConfig] = None):
        self.config = config or HandshakeConfig()
        self.pq_kem = PostQuantumKEM()
        self.sig = PostQuantumSignature()
        self._sessions: dict[str, AuthenticatedSession] = {}
        self._pending: dict[str, dict] = {}
        self.stats = {
            "handshakes_initiated": 0,
            "handshakes_completed": 0,
            "handshakes_failed": 0,
            "signatures_verified": 0,
            "macs_verified": 0,
        }

    def _derive_session_key(
        self,
        x25519_shared: bytes,
        mlkem_shared: bytes,
        initiator_id: str,
        responder_id: str,
    ) -> bytes:
        """Leitet den Session-Key ab (HKDF mit Domain Separation).

        Nutzt die zentrale KDF aus crypto/hybrid_kem.py:
          HKDF-SHA256(x25519_shared || mlkem_shared, info=context)

        Die info-String enthält (optional) initiator_id und responder_id,
        damit verschiedene Session-Paare unterschiedliche Keys ableiten.
        """
        if self.config.session_binding:
            info = f"erebos-auth-v1:{initiator_id}:{responder_id}".encode()
        else:
            info = b"erebos-auth-v1"
        return derive_hybrid_key(x25519_shared, mlkem_shared, info=info)

    def _compute_mac(
        self, session_key: bytes, role: str, initiator: str, responder: str
    ) -> bytes:
        """Berechnet MAC zur Key-Bestaetigung."""
        message = f"{initiator}:{responder}:{role}".encode()
        return hmac.new(session_key, message, hashlib.sha256).digest()

    def initiate(
        self,
        initiator_id: str,
        responder_pubkey: HybridKeyPair,
        responder_sigkey: bytes,
        initiator_sigkey: SignatureKeyPair,
    ) -> tuple[HandshakeMessage, dict]:
        """Startet den Handshake (Initiator-Seite)."""
        from cryptography.hazmat.primitives.asymmetric.x25519 import (
            X25519PrivateKey,
            X25519PublicKey,
        )
        from cryptography.hazmat.primitives import serialization

        ephemeral_priv = X25519PrivateKey.generate()
        ephemeral_pub = ephemeral_priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        # X25519 ephemeral exchange (ROHES Shared Secret)
        responder_x_pub = X25519PublicKey.from_public_bytes(
            responder_pubkey.x25519_public
        )
        x25519_shared = ephemeral_priv.exchange(responder_x_pub)

        # ML-KEM encapsulate (ROHES Shared Secret)
        mlkem_ct_bytes, mlkem_shared = self.pq_kem.encapsulate(
            responder_pubkey.mlkem_public
        )

        # Nachricht bauen
        msg = HandshakeMessage(
            sender_id=initiator_id,
            x25519_pub=ephemeral_pub,
            mlkem_ct=mlkem_ct_bytes,
        )

        # Signieren
        if self.config.use_signatures:
            msg.signature = self.sig.sign(
                msg.signable_bytes(), initiator_sigkey.private_key
            )

        # Zustand speichern
        state = {
            "ephemeral_priv": ephemeral_priv,
            "initiator_id": initiator_id,
            "timestamp": msg.timestamp,
            "x25519_shared": x25519_shared,
            "mlkem_shared": mlkem_shared,
        }
        self._pending[initiator_id] = state
        self.stats["handshakes_initiated"] += 1

        return msg, state

    def respond(
        self,
        responder_id: str,
        initiator_msg: HandshakeMessage,
        initiator_sigkey: bytes,
        responder_pubkey: HybridKeyPair,
        responder_sigkey: SignatureKeyPair,
    ) -> tuple[HandshakeMessage, dict]:
        """Antwortet auf den Handshake (Responder-Seite)."""
        if self.config.timestamp_check:
            if abs(time.time() - initiator_msg.timestamp) > self.config.max_timestamp_skew_seconds:
                self.stats["handshakes_failed"] += 1
                raise ValueError("Timestamp zu alt (Replay?)")

        if self.config.use_signatures:
            if not self.sig.verify(
                initiator_msg.signable_bytes(),
                initiator_msg.signature,
                initiator_sigkey,
            ):
                self.stats["handshakes_failed"] += 1
                raise ValueError("Initiator-Signatur ungueltig")
            self.stats["signatures_verified"] += 1

        from cryptography.hazmat.primitives.asymmetric.x25519 import (
            X25519PrivateKey,
            X25519PublicKey,
        )
        from cryptography.hazmat.primitives import serialization

        ephemeral_priv = X25519PrivateKey.generate()
        ephemeral_pub = ephemeral_priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        initiator_pub = X25519PublicKey.from_public_bytes(
            initiator_msg.x25519_pub
        )
        x25519_shared = ephemeral_priv.exchange(initiator_pub)

        # ML-KEM decapsulate (ROHES Shared Secret)
        mlkem_shared = self.pq_kem.decapsulate(
            initiator_msg.mlkem_ct,
            responder_pubkey.mlkem_private,
        )

        session_key = self._derive_session_key(
            x25519_shared,
            mlkem_shared,
            initiator_msg.sender_id,
            responder_id,
        )

        mac = b""
        if self.config.use_mac:
            mac = self._compute_mac(
                session_key, "responder", initiator_msg.sender_id, responder_id
            )

        msg = HandshakeMessage(
            sender_id=responder_id,
            x25519_pub=ephemeral_pub,
            mlkem_ct=b"",
            mac=mac,
        )

        if self.config.use_signatures:
            msg.signature = self.sig.sign(
                msg.signable_bytes(), responder_sigkey.private_key
            )

        state = {
            "session_key": session_key,
            "initiator_id": initiator_msg.sender_id,
            "responder_id": responder_id,
            "initiator_msg": initiator_msg,
            "x25519_shared": x25519_shared,
        }

        return msg, state

    def confirm(
        self,
        initiator_state: dict,
        responder_msg: HandshakeMessage,
        responder_sigkey: bytes,
        responder_pubkey: HybridKeyPair,
    ) -> AuthenticatedSession:
        """Bestaetigt den Handshake (Initiator-Seite)."""
        if self.config.timestamp_check:
            if abs(time.time() - responder_msg.timestamp) > self.config.max_timestamp_skew_seconds:
                self.stats["handshakes_failed"] += 1
                raise ValueError("Responder-Timestamp zu alt")

        if self.config.use_signatures:
            if not self.sig.verify(
                responder_msg.signable_bytes(),
                responder_msg.signature,
                responder_sigkey,
            ):
                self.stats["handshakes_failed"] += 1
                raise ValueError("Responder-Signatur ungueltig")
            self.stats["signatures_verified"] += 1

        from cryptography.hazmat.primitives.asymmetric.x25519 import (
            X25519PublicKey,
        )

        responder_pub = X25519PublicKey.from_public_bytes(
            responder_msg.x25519_pub
        )
        x25519_shared = initiator_state["ephemeral_priv"].exchange(responder_pub)

        # ML-KEM Shared aus urspruenglichem Encapsulate
        mlkem_shared = initiator_state["mlkem_shared"]

        session_key = self._derive_session_key(
            x25519_shared,
            mlkem_shared,
            initiator_state["initiator_id"],
            responder_msg.sender_id,
        )

        if self.config.use_mac:
            expected_mac = self._compute_mac(
                session_key,
                "responder",
                initiator_state["initiator_id"],
                responder_msg.sender_id,
            )
            if not hmac.compare_digest(responder_msg.mac, expected_mac):
                self.stats["handshakes_failed"] += 1
                raise ValueError("MAC ungueltig")
            self.stats["macs_verified"] += 1

        # ThreefishAEAD: CTR + HMAC-SHA256, HKDF-basierte Key-Ableitung.
        # (kein separates ThreefishCipher mehr — ECB war unsicher)
        aead = ThreefishAEAD.from_secret(
            session_key, info=b"erebos-auth-aead-v1",
        )

        session_id = hashlib.sha256(
            session_key + str(time.time()).encode()
        ).hexdigest()[:16]

        session = AuthenticatedSession(
            session_id=session_id,
            initiator_id=initiator_state["initiator_id"],
            responder_id=responder_msg.sender_id,
            session_key=session_key,
            aead=aead,
            state=HandshakeState.CONFIRMED,
            confirmed_at=time.time(),
        )
        self._sessions[session_id] = session
        self.stats["handshakes_completed"] += 1

        logger.info(
            f"Handshake abgeschlossen: {session_id} "
            f"({session.initiator_id} <-> {session.responder_id})"
        )
        return session

    def get_session(self, session_id: str) -> Optional[AuthenticatedSession]:
        """Gibt eine Session zurueck."""
        return self._sessions.get(session_id)

    def get_stats(self) -> dict:
        """Statistiken."""
        return {
            **self.stats,
            "active_sessions": len(self._sessions),
            "config": {
                "signatures": self.config.use_signatures,
                "mac": self.config.use_mac,
                "session_binding": self.config.session_binding,
                "timestamp_check": self.config.timestamp_check,
            },
        }
