"""Rendezvous-Mechanismus für Erebos-eigene Hidden Services."""

import json
import time
from dataclasses import dataclass, asdict
from typing import List, Optional

from .hidden_service import IntroPoint


@dataclass
class RendezvousRequest:
    client_ephemeral_key: bytes
    rendezvous_peer_id: str
    rendezvous_address: str
    created_at: float
    hidden_service_address: str = ""
    signature: bytes = b""

    def signable_payload(self) -> bytes:
        data = {
            "client_ephemeral_key": self.client_ephemeral_key.hex(),
            "rendezvous_peer_id": self.rendezvous_peer_id,
            "rendezvous_address": self.rendezvous_address,
            "created_at": self.created_at,
        }
        return json.dumps(data, sort_keys=True).encode("utf-8")

    def to_dict(self) -> dict:
        return {
            "client_ephemeral_key": self.client_ephemeral_key.hex(),
            "rendezvous_peer_id": self.rendezvous_peer_id,
            "rendezvous_address": self.rendezvous_address,
            "hidden_service_address": self.hidden_service_address,
            "created_at": self.created_at,
            "signature": self.signature.hex(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RendezvousRequest":
        return cls(
            client_ephemeral_key=bytes.fromhex(data["client_ephemeral_key"]),
            rendezvous_peer_id=data["rendezvous_peer_id"],
            rendezvous_address=data["rendezvous_address"],
            hidden_service_address=data.get("hidden_service_address", ""),
            created_at=data["created_at"],
            signature=bytes.fromhex(data["signature"]),
        )


@dataclass
class RendezvousResponse:
    status: str
    message: str
    created_at: float


def select_intro_points(descriptor, count: int = 3) -> List[IntroPoint]:
    return descriptor.intro_points[:count]


def build_rendezvous_request(client_ephemeral_key: bytes, rendezvous_peer_id: str, rendezvous_address: str) -> RendezvousRequest:
    return RendezvousRequest(
        client_ephemeral_key=client_ephemeral_key,
        rendezvous_peer_id=rendezvous_peer_id,
        rendezvous_address=rendezvous_address,
        created_at=time.time(),
    )
