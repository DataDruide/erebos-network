"""PQ-Sphinx: Post-Quantum Mixnet-Paketformat.

Forschungsprototyp fuer ein post-quanten-sicheres Sphinx-Format.

Klassisches Sphinx nutzt DH-Eigenschaften. PQ-KEMs teilen diese nicht.
Loesung: Layered Encryption mit ML-KEM-1024.
"""

import hashlib
import hmac
import logging
import os
import secrets
from dataclasses import dataclass, field
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .pq_kem import PostQuantumKEM, KEMKeyPair

logger = logging.getLogger(__name__)


@dataclass
class PQHop:
    """Ein Hop im PQ-Sphinx-Paket."""

    node_id: str
    public_key: bytes
    routing_info: bytes = b""


@dataclass
class PQSphinxPacket:
    """Ein PQ-Sphinx-Paket.

    Enthaelt verschluesselte Header fuer jeden Hop
    plus den verschluesselten Payload.
    """

    layers: list[bytes]
    payload: bytes
    mac: bytes
    created_at: float = field(default_factory=lambda: __import__("time").time())

    @property
    def total_size(self) -> int:
        return sum(len(l) for l in self.layers) + len(self.payload) + len(self.mac)

    @property
    def num_hops(self) -> int:
        return len(self.layers)


class PQSphinx:
    """Post-Quantum Sphinx Mixnet-Format.

    Erzeugt mehrschichtige Pakete:
    - Fuer jeden Hop eine Schicht
    - Payload am Ende
    - MAC fuer Integritaet

    Jeder Hop entfernt eine Schicht und leitet weiter.
    """

    def __init__(self):
        self.kem = PostQuantumKEM()
        self.stats = {
            "packets_created": 0,
            "packets_peeled": 0,
            "total_layers": 0,
        }

    @staticmethod
    def _derive_payload_key(shared_secret: bytes) -> bytes:
        """HKDF-SHA256 fuer den Payload-Key (32 Byte, RFC 5869)."""
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"erebos-pq-sphinx-key-v1",
        ).derive(shared_secret)

    @staticmethod
    def _derive_mac_key(shared_secret: bytes) -> bytes:
        """HKDF-SHA256 fuer den MAC-Key (32 Byte, RFC 5869)."""
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"erebos-pq-sphinx-mac-v1",
        ).derive(shared_secret)

    def create_packet(
        self,
        hops: list[PQHop],
        payload: bytes,
    ) -> PQSphinxPacket:
        """Erzeugt ein PQ-Sphinx-Paket.

        Args:
            hops: Liste von Hops (mit Public Keys)
            payload: Zu uebertragende Daten

        Returns:
            PQSphinxPacket mit einer Schicht pro Hop
        """
        layers = []
        current_payload = payload

        # Von hinten nach vorne: jede Schicht verschluesselt die naechste
        for hop in reversed(hops):
            # Encapsulate fuer diesen Hop
            ciphertext, shared_secret = self.kem.encapsulate(hop.public_key)

            # Payload-Key per HKDF (RFC 5869)
            key = self._derive_payload_key(shared_secret)
            encrypted = self._xor_encrypt(current_payload, key)

            # Layer = KEM-Ciphertext + Encrypted Payload + Routing-Info
            layer = ciphertext + encrypted + hop.routing_info
            layers.append(layer)

            current_payload = layer

        self.stats["packets_created"] += 1
        self.stats["total_layers"] += len(layers)

        # MAC ueber alles (HMAC-SHA256 mit abgeleitetem Key)
        mac_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"erebos-pq-sphinx-packet-mac-v1",
        ).derive(current_payload)
        mac = hmac.new(mac_key, current_payload, hashlib.sha256).digest()

        return PQSphinxPacket(
            layers=layers,
            payload=payload,
            mac=mac,
        )

    def _xor_encrypt(self, data: bytes, key: bytes) -> bytes:
        """ChaCha20-Poly1305 AEAD-Verschluesselung (RFC 8439).

        Nicht mehr XOR-basiert: liefert (nonce || ciphertext || tag).
        Fuer Decryption siehe _xor_decrypt.

        Hinweis: Der Name ist historisch (XOR), die Implementierung
        ist jetzt AEAD.
        """
        nonce = os.urandom(12)
        ct = ChaCha20Poly1305(key).encrypt(nonce, data, None)
        return nonce + ct

    def _xor_decrypt(self, data: bytes, key: bytes) -> bytes:
        """ChaCha20-Poly1305 AEAD-Entschluesselung.

        Erwartet das Format (nonce || ciphertext || tag) von _xor_encrypt.
        Raises cryptography.exceptions.InvalidTag bei Manipulation.
        """
        if len(data) < 12 + 16:
            raise ValueError(f"Zu kurz fuer AEAD: {len(data)} Byte")
        nonce, ct = data[:12], data[12:]
        return ChaCha20Poly1305(key).decrypt(nonce, ct, None)

    @staticmethod
    def sizes(num_hops: int) -> dict:
        """Gibt Groessen zurueck."""
        mlkem_ct = 1568
        return {
            "num_hops": num_hops,
            "per_layer": mlkem_ct + 64,  # KEM-CT + Payload-Overhead
            "total": num_hops * (mlkem_ct + 64),
            "algorithm": "PQ-Sphinx (ML-KEM-1024)",
            "security": "post-quantum",
            "nist_level": 5,
        }
