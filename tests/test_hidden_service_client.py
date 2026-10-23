import asyncio
from erebos_network.hidden_service import (
    derive_erebos_address,
    HiddenServiceDescriptor,
    IntroPoint,
    sign_descriptor,
)
from erebos_network.hidden_service_client import connect_to_hidden_service
from cryptography.hazmat.primitives.asymmetric import ed25519
import time


class MockDHT:
    def __init__(self):
        self.store = {}
    def put(self, key, value):
        self.store[key] = value
    def get(self, key):
        return self.store.get(key)


def test_connect_to_hidden_service():
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    address = derive_erebos_address(public_key)

    intro = IntroPoint(
        peer_id="peer1",
        address="127.0.0.1:9999",
        public_key=ed25519.Ed25519PrivateKey.generate().public_key().public_bytes_raw(),
    )

    descriptor = HiddenServiceDescriptor(
        address=address,
        public_key=public_key,
        intro_points=[intro],
        created_at=time.time(),
        ttl_seconds=3600,
    )
    sign_descriptor(descriptor, private_key)

    dht = MockDHT()
    import hashlib
    key = hashlib.sha256(address.encode()).digest()
    dht.put(key, descriptor.to_dict())

    request = asyncio.run(connect_to_hidden_service(
        address=address,
        dht=dht,
        rendezvous_peer_id="peer2",
        rendezvous_address="127.0.0.1:9998",
        client_ephemeral_key=b"\x02" * 32,
    ))
    assert request is not None
    assert request.rendezvous_peer_id == "peer2"
    assert request.rendezvous_address == "127.0.0.1:9998"
