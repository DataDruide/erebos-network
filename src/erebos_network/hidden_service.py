"""Erebos-eigene Hidden Services: Adressformat und Descriptor-Struktur."""

import hashlib
import base64
import json
import time
from dataclasses import dataclass, asdict, field
from typing import List, Optional

from cryptography.hazmat.primitives.asymmetric import ed25519


def derive_erebos_address(public_key_bytes: bytes) -> str:
    digest = hashlib.sha256(public_key_bytes).digest()
    encoded = base64.b32encode(digest).decode("ascii").rstrip("=").lower()
    return encoded + ".erebos"


@dataclass
class IntroPoint:
    peer_id: str
    address: str
    public_key: bytes


@dataclass
class HiddenServiceDescriptor:
    address: str
    public_key: bytes
    intro_points: List[IntroPoint]
    created_at: float
    ttl_seconds: int
    signature: bytes = b""

    def signable_payload(self) -> bytes:
        data = {
            "address": self.address,
            "public_key": self.public_key.hex(),
            "intro_points": [
                {"peer_id": ip.peer_id, "address": ip.address, "public_key": ip.public_key.hex()}
                for ip in self.intro_points
            ],
            "created_at": self.created_at,
            "ttl_seconds": self.ttl_seconds,
        }
        return json.dumps(data, sort_keys=True).encode("utf-8")

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "public_key": self.public_key.hex(),
            "intro_points": [
                {"peer_id": ip.peer_id, "address": ip.address, "public_key": ip.public_key.hex()}
                for ip in self.intro_points
            ],
            "created_at": self.created_at,
            "ttl_seconds": self.ttl_seconds,
            "signature": self.signature.hex(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "HiddenServiceDescriptor":
        intro_points = [
            IntroPoint(peer_id=ip["peer_id"], address=ip["address"], public_key=bytes.fromhex(ip["public_key"]))
            for ip in data["intro_points"]
        ]
        return cls(
            address=data["address"],
            public_key=bytes.fromhex(data["public_key"]),
            intro_points=intro_points,
            created_at=data["created_at"],
            ttl_seconds=data["ttl_seconds"],
            signature=bytes.fromhex(data["signature"]),
        )

    def is_expired(self) -> bool:
        return time.time() > self.created_at + self.ttl_seconds


def sign_descriptor(descriptor: HiddenServiceDescriptor, private_key: ed25519.Ed25519PrivateKey) -> HiddenServiceDescriptor:
    payload = descriptor.signable_payload()
    descriptor.signature = private_key.sign(payload)
    return descriptor


def verify_descriptor(descriptor: HiddenServiceDescriptor) -> bool:
    try:
        public_key = ed25519.Ed25519PublicKey.from_public_bytes(descriptor.public_key)
        public_key.verify(descriptor.signature, descriptor.signable_payload())
        return True
    except Exception:
        return False


def publish_descriptor(dht, descriptor: HiddenServiceDescriptor) -> None:
    key = hashlib.sha256(descriptor.address.encode()).digest()
    dht.put(key, descriptor.to_dict())


def lookup_descriptor(dht, address: str) -> Optional[HiddenServiceDescriptor]:
    key = hashlib.sha256(address.encode()).digest()
    data = dht.get(key)
    if data is None:
        return None
    descriptor = HiddenServiceDescriptor.from_dict(data)
    if not verify_descriptor(descriptor):
        return None
    if descriptor.is_expired():
        return None
    return descriptor
