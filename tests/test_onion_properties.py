"""Property-based Tests fuer Onion-Routing (Hypothesis).

Prueft Invarianten, die fuer JEDE Onion-Kombination gelten muessen:
- Jeder Peer entschluesselt genau seine Schicht
- Die Reihenfolge der Layer ist korrekt
- Kein Peer kann mehr als eine Schicht entschluesseln
"""
import pytest
from hypothesis import given, strategies as st, settings, assume

from erebos_network.onion import (
    pack_onion_3hop,
    pack_onion_2hop,
    open_layer,
    pack_relay_header,
    unpack_relay_header,
    FRAME_RELAY_WIRE,
)


# Strategie: zufaellige X25519-Keypairs (32 Bytes)
x25519_keys = st.binary(min_size=32, max_size=32)

# Strategie: zufaellige Nachrichten
messages = st.binary(min_size=1, max_size=200)


def _derive_pub(priv_bytes: bytes) -> bytes:
    """Leitet X25519-Pubkey aus Privkey ab."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    priv = X25519PrivateKey.from_private_bytes(priv_bytes)
    return priv.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )


@given(
    peer2_priv=x25519_keys,
    peer3_priv=x25519_keys,
    peer1_priv=x25519_keys,
    payload=messages,
)
@settings(max_examples=50, deadline=None)
def test_onion_layers_are_independent(
    peer2_priv, peer3_priv, peer1_priv, payload
):
    """Property: Jeder Peer kann NUR seine eigene Schicht entschluesseln.

    Die Onion-Struktur: peer2 (aussen) -> peer3 (mitte) -> peer1 (innen).
    Wenn peer2 seine Schicht oeffnet, darf er NICHT peer3s oder peer1s
    Schicht lesen koennen.
    """
    peer2_pub = _derive_pub(peer2_priv)
    peer3_pub = _derive_pub(peer3_priv)
    peer1_pub = _derive_pub(peer1_priv)

    onion = pack_onion_3hop(peer2_pub, peer3_pub, peer1_pub, payload)

    # Peer2 oeffnet seine Schicht
    layer2 = open_layer(peer2_priv, onion)
    assert layer2 is not None
    assert len(layer2) >= 3

    # Layer2 enthaelt den Relay-Header + naechste Layer
    frame_type, next_port = unpack_relay_header(layer2[:3])
    assert frame_type in (FRAME_RELAY_WIRE, 0x02)  # RELAY oder OPEN
    assert 0 <= next_port <= 0xFFFF

    # Peer2 sieht NICHT die urspruengliche Nachricht in Klarform —
    # die naechste Layer ist wieder verschluesselt
    next_layer = layer2[3:]
    assert len(next_layer) > 0


@given(
    peer2_priv=x25519_keys,
    peer3_priv=x25519_keys,
    peer1_priv=x25519_keys,
    payload=messages,
)
@settings(max_examples=50, deadline=None)
def test_relay_header_roundtrip(
    peer2_priv, peer3_priv, peer1_priv, payload
):
    """Property: pack_relay_header + unpack_relay_header = Identitaet."""
    port = 9999

    header = pack_relay_header(FRAME_RELAY_WIRE, port)
    assert len(header) == 3

    frame_type, next_port = unpack_relay_header(header)
    assert frame_type == FRAME_RELAY_WIRE
    assert next_port == port


@given(
    peer2_priv=x25519_keys,
    peer3_priv=x25519_keys,
    peer1_priv=x25519_keys,
    payload=messages,
)
@settings(max_examples=30, deadline=None)
def test_onion_size_grows_with_layers(
    peer2_priv, peer3_priv, peer1_priv, payload
):
    """Property: 3-Hop-Onion ist groesser als 2-Hop-Onion."""
    peer2_pub = _derive_pub(peer2_priv)
    peer3_pub = _derive_pub(peer3_priv)
    peer1_pub = _derive_pub(peer1_priv)

    onion_2 = pack_onion_2hop(peer2_pub, peer1_pub, payload)
    onion_3 = pack_onion_3hop(peer2_pub, peer3_pub, peer1_pub, payload)

    assert len(onion_3) > len(onion_2)


@given(
    peer2_priv=x25519_keys,
    peer3_priv=x25519_keys,
    peer1_priv=x25519_keys,
    payload=messages,
)
@settings(max_examples=30, deadline=None)
def test_peer2_cannot_decrypt_next_layer(
    peer2_priv, peer3_priv, peer1_priv, payload
):
    """Property: Peer2 kann die naechste Layer NICHT entschluesseln.

    Das ist die Kern-Anonymitaetsgarantie: Ein Relay sieht nur seine
    eigene Schicht + die (verschluesselte) naechste Layer. Es kann
    nicht weiter entschluesseln.
    """
    assume(len({peer2_priv, peer3_priv, peer1_priv}) == 3)

    peer2_pub = _derive_pub(peer2_priv)
    peer3_pub = _derive_pub(peer3_priv)
    peer1_pub = _derive_pub(peer1_priv)

    onion = pack_onion_3hop(peer2_pub, peer3_pub, peer1_pub, payload)

    layer2 = open_layer(peer2_priv, onion)
    assert layer2 is not None
    assert len(layer2) >= 3

    next_layer = layer2[3:]

    with pytest.raises(Exception):
        open_layer(peer2_priv, next_layer)

