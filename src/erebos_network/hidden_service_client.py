"""Client-Seite für Erebos-eigene Hidden Services."""

import asyncio
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
) -> Optional[RendezvousRequest]:
    """
    Verbindet sich mit einem Hidden Service über einen Rendezvous-Punkt.
    
    Ablauf:
    1. Descriptor aus der DHT holen.
    2. Rendezvous-Request bauen.
    3. Anfrage an den ersten Intro-Point schicken.
    4. Auf Antwort warten (kommt später).
    """
    logger.info(f"Suche Descriptor für {address}")
    descriptor = lookup_descriptor(dht, address)
    if descriptor is None:
        logger.error(f"Kein Descriptor für {address} gefunden")
        return None
    
    if not descriptor.intro_points:
        logger.error(f"Descriptor für {address} hat keine Intro-Points")
        return None
    
    intro_point = descriptor.intro_points[0]
    logger.info(f"Wähle Intro-Point {intro_point.peer_id} ({intro_point.address})")
    
    request = build_rendezvous_request(
        client_ephemeral_key=client_ephemeral_key,
        rendezvous_peer_id=rendezvous_peer_id,
        rendezvous_address=rendezvous_address,
    )
    
    logger.info(f"Sende Rendezvous-Request an {intro_point.address}")
    # Hier würde die tatsächliche Netzwerkkommunikation stattfinden.
    # Für den Moment geben wir den Request zurück (als Platzhalter).
    return request
