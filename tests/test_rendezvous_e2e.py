"""End-to-End-Test für den Rendezvous-Mechanismus.

Simuliert die komplette Kette:
1. Client holt Descriptor aus der DHT.
2. Client baut Rendezvous-Request.
3. Client sendet Request an Intro-Point.
4. Intro-Point leitet Request an Hidden Service weiter.
5. Hidden Service verarbeitet Request und baut Tunnel zum Rendezvous-Punkt.
6. Antwort geht zurück zum Client.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock

from cryptography.hazmat.primitives.asymmetric import ed25519

from erebos_network.hidden_service import (
    derive_erebos_address,
    HiddenServiceDescriptor,
    IntroPoint,
    sign_descriptor,
)
from erebos_network.hidden_service_client import connect_to_hidden_service
from erebos_network.hidden_service_server import handle_rendezvous_request
from erebos_network.rendezvous import (
    build_rendezvous_request,
    RendezvousRequest,
)


class MockDHT:
    def __init__(self):
        self.store = {}

    def put(self, key, value):
        self.store[key] = value

    def get(self, key):
        return self.store.get(key)


def test_full_rendezvous_e2e():
    """Kompletter Durchlauf: Client → Intro-Point → Hidden Service."""
    # 1. Hidden Service generiert Schlüssel und Adresse
    hs_private = ed25519.Ed25519PrivateKey.generate()
    hs_public = hs_private.public_key().public_bytes_raw()
    hs_address = derive_erebos_address(hs_public)

    # 2. Intro-Points definieren
    intro1 = IntroPoint(
        peer_id="peer1",
        address="127.0.0.1:9999",
        public_key=ed25519.Ed25519PrivateKey.generate().public_key().public_bytes_raw(),
    )
    intro2 = IntroPoint(
        peer_id="peer2",
        address="127.0.0.1:9998",
        public_key=ed25519.Ed25519PrivateKey.generate().public_key().public_bytes_raw(),
    )

    # 3. Descriptor erstellen und signieren
    descriptor = HiddenServiceDescriptor(
        address=hs_address,
        public_key=hs_public,
        intro_points=[intro1, intro2],
        created_at=time.time(),
        ttl_seconds=3600,
    )
    sign_descriptor(descriptor, hs_private)

    # 4. Descriptor in DHT veröffentlichen
    dht = MockDHT()
    import hashlib
    key = hashlib.sha256(hs_address.encode()).digest()
    dht.put(key, descriptor.to_dict())

    # 5. Client baut Rendezvous-Request
    client_ephemeral = b"\x01" * 32
    rendezvous_peer = "peer3"
    rendezvous_address = "127.0.0.1:9997"

    request = asyncio.run(connect_to_hidden_service(
        address=hs_address,
        dht=dht,
        rendezvous_peer_id=rendezvous_peer,
        rendezvous_address=rendezvous_address,
        client_ephemeral_key=client_ephemeral,
    ))

    # 6. Prüfen: Request wurde gebaut
    assert request is not None
    assert request.rendezvous_peer_id == rendezvous_peer
    assert request.rendezvous_address == rendezvous_address
    assert request.client_ephemeral_key == client_ephemeral

    # 7. Hidden Service verarbeitet die Anfrage
    async def tunnel_factory(address):
        # Simuliert einen Tunnel-Aufbau zum Rendezvous-Punkt
        return MagicMock()

    response = asyncio.run(handle_rendezvous_request(request, tunnel_factory))

    # 8. Prüfen: Antwort ist ok
    assert response.status == "ok"
    assert "Rendezvous" in response.message or "Tunnel" in response.message


def test_rendezvous_with_invalid_tunnel():
    """Fehlerfall: Tunnel-Aufbau schlägt fehl."""
    async def failing_tunnel_factory(address):
        raise ConnectionError("Tunnel-Aufbau fehlgeschlagen")

    request = RendezvousRequest(
        client_ephemeral_key=b"\x01" * 32,
        rendezvous_peer_id="peer3",
        rendezvous_address="127.0.0.1:9997",
        created_at=time.time(),
    )

    response = asyncio.run(handle_rendezvous_request(request, failing_tunnel_factory))
    assert response.status == "error"
    assert "fehlgeschlagen" in response.message.lower()
