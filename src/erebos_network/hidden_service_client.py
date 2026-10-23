"""Client-Seite für Erebos-eigene Hidden Services."""

import asyncio
import json
import logging
from typing import Optional

from .hidden_service import HiddenServiceDescriptor, lookup_descriptor
from .rendezvous import RendezvousRequest, build_rendezvous_request

logger = logging.getLogger(__name__)


async def connect_to_hidden_service(
    address: str,
    dht,
    rendezvous_peer_id: str,
    rendezvous_address: str,
    client_ephemeral_key: bytes,
    use_network: bool = False,
) -> Optional[RendezvousRequest]:
    """
    Verbindet sich mit einem Hidden Service über einen Rendezvous-Punkt.

    Args:
        address: Die .erebos-Adresse.
        dht: Die DHT (DistributedDescriptorStore oder DescriptorStore).
        rendezvous_peer_id: Die Peer-ID des Rendezvous-Punkts.
        rendezvous_address: Die Adresse des Rendezvous-Punkts (host:port).
        client_ephemeral_key: Der X25519-Public-Key des Clients.
        use_network: Wenn True, wird async_get() für die Netzwerkabfrage genutzt.

    Returns:
        Der Rendezvous-Request, oder None bei Fehler.
    """
    logger.info(f"Suche Descriptor für {address}")

    # 1. Descriptor holen (lokal oder über Netzwerk)
    descriptor = None
    if use_network and hasattr(dht, "async_get"):
        import hashlib
        key = hashlib.sha256(address.encode()).digest()
        descriptor_dict = await dht.async_get(key)
        if descriptor_dict:
            descriptor = HiddenServiceDescriptor.from_dict(descriptor_dict)
    else:
        descriptor = lookup_descriptor(dht, address)

    if descriptor is None:
        logger.error(f"Kein Descriptor für {address} gefunden")
        return None

    if not descriptor.intro_points:
        logger.error(f"Descriptor für {address} hat keine Intro-Points")
        return None

    # 2. Intro-Point wählen (erster)
    intro_point = descriptor.intro_points[0]
    logger.info(f"Wähle Intro-Point {intro_point.peer_id} ({intro_point.address})")

    # 3. Rendezvous-Request bauen
    request = build_rendezvous_request(
        client_ephemeral_key=client_ephemeral_key,
        rendezvous_peer_id=rendezvous_peer_id,
        rendezvous_address=rendezvous_address,
    )

    logger.info(f"Sende Rendezvous-Request an {intro_point.address}")
    return request


async def send_rendezvous_over_tunnel(
    tunnel_client,
    request: RendezvousRequest,
) -> None:
    """Sendet eine Rendezvous-Anfrage über einen bestehenden Tunnel."""
    payload = request.to_dict()
    await tunnel_client.send_rendezvous_request(payload)
    logger.info(f"Rendezvous-Request gesendet an {tunnel_client.peer_name}")


async def receive_rendezvous_response(tunnel_client) -> Optional[dict]:
    """Wartet auf eine Rendezvous-Antwort über den Tunnel."""
    try:
        raw = await asyncio.wait_for(tunnel_client.receive(), timeout=10.0)
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))
    except asyncio.TimeoutError:
        logger.error("Timeout beim Warten auf Rendezvous-Antwort")
        return None
