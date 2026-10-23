"""End-to-End-Test für die verteilte DHT.

Ein Peer läuft. Ein Descriptor wird direkt an ihn gesendet.
Ein zweiter Client holt ihn über async_get().
"""

import asyncio
import hashlib
import time
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from erebos_network.dht import PeerInfo
from erebos_network.distributed_dht import DistributedDescriptorStore
from erebos_network.hidden_service import (
    derive_erebos_address,
    HiddenServiceDescriptor,
    IntroPoint,
    sign_descriptor,
)
from erebos_network.tunnel import run_peer_server


@pytest.mark.asyncio
async def test_dht_put_get_over_real_peers():
    """Descriptor wird direkt an einen Peer gesendet und von einem anderen geholt."""
    port = 9997
    peer_task = asyncio.create_task(
        run_peer_server(port=port, ack_cover=False, host="127.0.0.1")
    )
    await asyncio.sleep(0.5)

    try:
        # 1. Descriptor erstellen
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

        # 2. DHT-Knoten erstellen (kennt den Peer)
        dht = DistributedDescriptorStore("00" * 32)
        peer1 = PeerInfo(peer_id="11" * 32, address="127.0.0.1:9997")
        dht.add_peer(peer1)

        # 3. Descriptor direkt an den Peer senden (ohne Routing)
        key = hashlib.sha256(hs_address.encode()).digest()
        # Wir senden direkt über einen Tunnel
        from erebos_network.tunnel import ErebosTunnelClient, FRAME_DHT_PUT
        client = ErebosTunnelClient(host="127.0.0.1", port=9997)
        await client.connect()
        import json
        payload = json.dumps({"key": key.hex(), "value": descriptor.to_dict()}).encode("utf-8")
        await client.send_typed(FRAME_DHT_PUT, payload)
        await client.close()
        await asyncio.sleep(0.5)

        # 4. Descriptor über dht.async_get() holen
        result = await dht.async_get(key)
        assert result is not None
        assert result["address"] == hs_address
    finally:
        peer_task.cancel()
        try:
            await peer_task
        except asyncio.CancelledError:
            pass
