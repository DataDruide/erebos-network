"""End-to-End-Test für den SOCKS5-Proxy mit .erebos-Adressen.

Startet einen Peer-Server, registriert einen Hidden Service im
DescriptorStore und simuliert einen SOCKS5-Client, der eine
.erebos-Adresse auflöst.
"""

import asyncio
import json
import hashlib
import time
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from erebos_network.hidden_service import (
    derive_erebos_address,
    HiddenServiceDescriptor,
    IntroPoint,
    sign_descriptor,
)
from erebos_network.distributed_dht import DistributedDescriptorStore
from erebos_network.dht import PeerInfo
from erebos_network.tunnel import run_peer_server


@pytest.mark.asyncio
async def test_proxy_resolves_erebos_address():
    """Simuliert den SOCKS5-Proxy und prüft die .erebos-Auflösung."""
    port = 9997
    peer_task = asyncio.create_task(
        run_peer_server(port=port, ack_cover=False, host="127.0.0.1")
    )
    await asyncio.sleep(0.5)

    try:
        # 1. Hidden Service erstellen
        hs_private = ed25519.Ed25519PrivateKey.generate()
        hs_public = hs_private.public_key().public_bytes_raw()
        hs_address = derive_erebos_address(hs_public)

        intro = IntroPoint(
            peer_id="peer1",
            address="127.0.0.1:9997",
            public_key=hs_private.public_key().public_bytes_raw(),
        )
        descriptor = HiddenServiceDescriptor(
            address=hs_address,
            public_key=hs_public,
            intro_points=[intro],
            created_at=time.time(),
            ttl_seconds=3600,
        )
        sign_descriptor(descriptor, hs_private)

        # 2. DHT-Knoten erstellen und Descriptor verteilen
        dht = DistributedDescriptorStore("00" * 32)
        peer1 = PeerInfo(peer_id="11" * 32, address="127.0.0.1:9997")
        dht.add_peer(peer1)

        key = hashlib.sha256(hs_address.encode()).digest()
        dht.put(key, descriptor.to_dict())
        await asyncio.sleep(0.5)

        # 3. Client-Seite: Descriptor über DHT holen und Rendezvous-Request bauen
        from erebos_network.hidden_service_client import connect_to_hidden_service
        request = await connect_to_hidden_service(
            address=hs_address,
            dht=dht,
            rendezvous_peer_id="peer2",
            rendezvous_address="127.0.0.1:9998",
            client_ephemeral_key=b"\x01" * 32,
            use_network=True,
        )

        assert request is not None
        assert request.rendezvous_peer_id == "peer2"
        assert request.rendezvous_address == "127.0.0.1:9998"

        # 4. Rendezvous-Request über Tunnel an den Intro-Point senden
        from erebos_network.tunnel import ErebosTunnelClient
        client = ErebosTunnelClient(host="127.0.0.1", port=9997)
        await client.connect()
        await client.send_rendezvous_request(request.to_dict())

        # 5. Auf Antwort warten
        raw = await asyncio.wait_for(client.receive(), timeout=5.0)
        assert raw is not None
        response = json.loads(raw.decode("utf-8"))
        assert "status" in response
        assert response["status"] in ("ok", "error")

        await client.close()
    finally:
        peer_task.cancel()
        try:
            await peer_task
        except asyncio.CancelledError:
            pass
