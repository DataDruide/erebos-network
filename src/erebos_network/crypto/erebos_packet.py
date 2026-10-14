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

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
import logging
import secrets
import struct
from dataclasses import dataclass, field
from typing import Optional

from .pq_kem import PostQuantumKEM, KEMKeyPair
from .threefish import ThreefishCipher

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

    VERSION = 1
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

    def _derive_threefish_key(self, shared_secret: bytes, context: bytes) -> bytes:
        """Leitet einen Threefish-512-Key (64 Bytes) per HKDF ab.

        RFC 5869: HKDF-SHA256, mit Domain Separation via info.
        Der context wird als info-Suffix verwendet, damit verschiedene
        Zwecke unterschiedliche Keys liefern.
        """
        return HKDF(
            algorithm=hashes.SHA256(),
            length=64,
            salt=None,
            info=b"erebos-packet-threefish-v1:" + context,
        ).derive(shared_secret)

    def _derive_mac_key(self, shared_secret: bytes) -> bytes:
        """Leitet einen HMAC-Key (32 Bytes) per HKDF ab.

        Vermeidet, dass rohe Shared Secrets direkt als HMAC-Key
        verwendet werden. RFC 5869.
        """
        return HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"erebos-packet-mac-v1",
        ).derive(shared_secret)

    def _derive_tweak(self, shared_secret: bytes) -> bytes:
        """Leitet einen Tweak (16 Bytes) per HKDF ab.

        RFC 5869: HKDF-SHA256, mit Domain Separation via info.
        Keine Truncation mehr (length=16 direkt).
        """
        return HKDF(
            algorithm=hashes.SHA256(),
            length=16,
            salt=None,
            info=b"erebos-packet-tweak-v1",
        ).derive(shared_secret)

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

            threefish_key = self._derive_threefish_key(
                shared_secret, b"erebos-packet-layer"
            )
            tweak = self._derive_tweak(shared_secret)

            cipher = ThreefishCipher(key=threefish_key, tweak=tweak)

            padded = self._pad(current)
            encrypted = cipher.encrypt(padded)

            mac_key = self._derive_mac_key(shared_secret)
            layer_mac = hmac.new(
                mac_key,
                ciphertext + encrypted + hop.routing_info,
                hashlib.sha256,
            ).digest()

            layer = (
                ciphertext
                + struct.pack(">H", len(hop.routing_info))
                + hop.routing_info
                + encrypted
                + layer_mac
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

        layer_mac = layer[-32:]
        encrypted = layer[ri_start+ri_len:-32]

        shared_secret = self.kem.decapsulate(
            self._make_ciphertext(kem_ct), keypair
        )

        mac_key = self._derive_mac_key(shared_secret)
        expected_mac = hmac.new(
            mac_key,
            kem_ct + encrypted + routing_info,
            hashlib.sha256,
        ).digest()

        if not hmac.compare_digest(layer_mac, expected_mac):
            raise PacketError("Layer-MAC ungueltig")

        threefish_key = self._derive_threefish_key(
            shared_secret, b"erebos-packet-layer"
        )
        tweak = self._derive_tweak(shared_secret)

        cipher = ThreefishCipher(key=threefish_key, tweak=tweak)
        decrypted = cipher.decrypt(encrypted)

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
