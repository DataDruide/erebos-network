"""Erebos Packet Format: Sphinx-kompatibel, KEM-basiert.

Basiert auf Outfox (2026): Vereinfachtes Sphinx-Format fuer
Post-Quanten-KEMs. Feste Routenlaenge, KEM-basierte Layer.

Sicherheitseigenschaften:
- Onion-Unpredictability
- Layer-Unlinkability
- Post-Quanten-Sicherheit (ML-KEM-1024)
"""

import hashlib
import hmac

import logging
import secrets
import struct
from dataclasses import dataclass, field
from typing import Optional

from .pq_kem import PostQuantumKEM, KEMKeyPair
from .threefish import ThreefishAEAD

logger = logging.getLogger(__name__)


class PacketError(Exception):
    """Fehler im Paketformat."""
    pass


@dataclass
class HopInfo:
    """Information ueber einen Hop im Pfad."""

    node_id: str
    public_key: bytes
    routing_info: bytes = b""

    @property
    def address(self) -> str:
        return f"{self.node_id}.erebos"


@dataclass
class ErebosPacket:
    """Ein Erebos-Paket."""

    layers: list[bytes]
    payload: bytes
    mac: bytes
    num_hops: int
    created_at: float = field(default_factory=lambda: __import__("time").time())

    @property
    def total_size(self) -> int:
        return sum(len(l) for l in self.layers) + len(self.payload) + len(self.mac)

    @property
    def is_valid_size(self) -> bool:
        return self.total_size > 0 and self.num_hops > 0


class ErebosPacketFormat:
    """Erebos-Paketformat (Outfox-Ansatz).

    Unterschied zu Sphinx:
    - Keine DH-Eigenschaften (KEM-basiert)
    - Feste Routenlaenge
    - Explizite MAC pro Layer
    """

    VERSION = 2
    MAGIC = b"EREBOS"
    MAX_HOPS = 7
    MIN_HOPS = 2

    def __init__(self):
        self.kem = PostQuantumKEM()
        self.stats = {
            "packets_created": 0,
            "packets_peeled": 0,
            "bytes_created": 0,
        }

    def create_packet(
        self,
        hops: list[HopInfo],
        payload: bytes,
        session_key: Optional[bytes] = None,
    ) -> ErebosPacket:
        """Erstellt ein Erebos-Paket."""
        if len(hops) < self.MIN_HOPS:
            raise PacketError(
                f"Zu wenige Hops: {len(hops)} < {self.MIN_HOPS}"
            )
        if len(hops) > self.MAX_HOPS:
            raise PacketError(
                f"Zu viele Hops: {len(hops)} > {self.MAX_HOPS}"
            )

        if session_key is None:
            session_key = secrets.token_bytes(32)

        layers = []
        current = payload

        for hop in reversed(hops):
            ciphertext, shared_secret = self.kem.encapsulate(hop.public_key)

            # ThreefishAEAD: CTR + HMAC-SHA256 (Layer-Integritaet)
            aead = ThreefishAEAD.from_secret(
                shared_secret, info=b"erebos-packet-layer-v2",
            )
            encrypted = aead.encrypt(current)

            # Layer-Format v2: kem_ct || ri_len(2B) || routing_info || aead_ct
            # (aead_ct enthaelt nonce + ciphertext + tag)
            layer = (
                ciphertext
                + struct.pack(">H", len(hop.routing_info))
                + hop.routing_info
                + encrypted
            )
            layers.append(layer)
            current = layer

        total_mac = hmac.new(
            session_key,
            current,
            hashlib.sha256,
        ).digest()

        packet = ErebosPacket(
            layers=layers,
            payload=payload,
            mac=total_mac,
            num_hops=len(hops),
        )

        self.stats["packets_created"] += 1
        self.stats["bytes_created"] += packet.total_size

        logger.info(
            f"Paket erstellt: {len(hops)} Hops, "
            f"{packet.total_size} Bytes"
        )
        return packet

    def peel_layer(
        self,
        packet: ErebosPacket,
        keypair: KEMKeyPair,
        layer_index: int = 0,
    ) -> tuple[Optional[bytes], bytes]:
        """Entfernt eine Schicht vom Paket.

        Args:
            packet: Das Paket
            keypair: KeyPair des aktuellen Hops
            layer_index: Welche Schicht

        Returns:
            (naechster_layer, routing_info)
        """
        if layer_index >= len(packet.layers):
            raise PacketError(f"Layer {layer_index} existiert nicht")

        layer = packet.layers[layer_index]

        kem_ct_size = 1568
        kem_ct = layer[:kem_ct_size]

        ri_len = struct.unpack(">H", layer[kem_ct_size:kem_ct_size+2])[0]
        ri_start = kem_ct_size + 2
        routing_info = layer[ri_start:ri_start+ri_len]

        # Layer-Format v2: aead_ct = nonce(16) || ciphertext || tag(32)
        encrypted = layer[ri_start+ri_len:]

        shared_secret = self.kem.decapsulate(
            self._make_ciphertext(kem_ct), keypair
        )

        aead = ThreefishAEAD.from_secret(
            shared_secret, info=b"erebos-packet-layer-v2",
        )
        try:
            decrypted = aead.decrypt(encrypted)
        except ValueError as e:
            raise PacketError(f"Layer-AEAD ungueltig: {e}")

        next_layer = None
        if layer_index + 1 < len(packet.layers):
            next_layer = decrypted

        self.stats["packets_peeled"] += 1

        return next_layer, routing_info

    def _make_ciphertext(self, mlkem_ct: bytes):
        """Erstellt ein HybridCiphertext-Objekt."""
        from .hybrid_kem import HybridCiphertext
        return HybridCiphertext(
            x25519_ephemeral_public=b"",
            mlkem_ciphertext=mlkem_ct,
        )

    @staticmethod
    def _pad(data: bytes, block_size: int = 64) -> bytes:
        """PKCS#7-aehnliches Padding."""
        padding_length = block_size - (len(data) % block_size)
        if padding_length == 0:
            padding_length = block_size
        return data + bytes([padding_length] * padding_length)

    @staticmethod
    def _unpad(data: bytes) -> bytes:
        """Entfernt Padding."""
        if not data:
            return data
        padding_length = data[-1]
        return data[:-padding_length]

    @staticmethod
    def sizes(num_hops: int) -> dict:
        """Gibt Groessen zurueck."""
        per_layer = 1568 + 2 + 64 + 32
        return {
            "version": ErebosPacketFormat.VERSION,
            "magic": ErebosPacketFormat.MAGIC.decode(),
            "num_hops": num_hops,
            "per_layer": per_layer,
            "total": num_hops * per_layer,
            "max_hops": ErebosPacketFormat.MAX_HOPS,
            "min_hops": ErebosPacketFormat.MIN_HOPS,
        }
