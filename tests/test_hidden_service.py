import time
from cryptography.hazmat.primitives.asymmetric import ed25519

from erebos_network.hidden_service import (
    derive_erebos_address,
    HiddenServiceDescriptor,
    IntroPoint,
    sign_descriptor,
    verify_descriptor,
)


def test_address_derivation():
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes_raw()
    address = derive_erebos_address(public_key)
    assert address.endswith(".erebos")
    assert len(address) == 52 + len(".erebos")


def test_descriptor_sign_and_verify():
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

    assert verify_descriptor(descriptor) is True

    descriptor.ttl_seconds = 7200
    assert verify_descriptor(descriptor) is False
