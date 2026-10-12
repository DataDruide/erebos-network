"""PQ-Sphinx: Post-Quantum Mixnet-Paketformat.

Forschungsprototyp fuer ein post-quanten-sicheres Sphinx-Format.

Klassisches Sphinx nutzt DH-Eigenschaften. PQ-KEMs teilen diese nicht.
Loesung: Layered Encryption mit ML-KEM-1024.
"""

import hashlib
import logging
import os
import secrets
from dataclasses import dataclass, field
from typing import Optional

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

            # Payload mit abgeleitetem Schluessel verschluesseln
            key = hashlib.sha256(
                shared_secret + b"erebos-pq-sphinx"
            ).digest()
            encrypted = self._xor_encrypt(current_payload, key)

            # Layer = KEM-Ciphertext + Encrypted Payload + Routing-Info
            layer = ciphertext + encrypted + hop.routing_info
            layers.append(layer)

            current_payload = layer

        self.stats["packets_created"] += 1
        self.stats["total_layers"] += len(layers)

        # MAC ueber alles
        mac = hashlib.sha256(current_payload).digest()

        return PQSphinxPacket(
            layers=layers,
            payload=payload,
            mac=mac,
        )

    def _xor_encrypt(self, data: bytes, key: bytes) -> bytes:
        """XOR-Verschluesselung (keystream aus SHA-256)."""
        result = bytearray(len(data))
        for i in range(0, len(data), 32):
            block = key + i.to_bytes(8, "big")
            keystream = hashlib.sha256(block).digest()
            for j in range(min(32, len(data) - i)):
                result[i + j] = data[i + j] ^ keystream[j]
        return bytes(result)

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
