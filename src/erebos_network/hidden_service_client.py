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
) -> Optional[RendezvousRequest]:
    """
    Verbindet sich mit einem Hidden Service über einen Rendezvous-Punkt.

    Ablauf:
    1. Descriptor aus der DHT holen.
    2. Rendezvous-Request bauen.
    3. Anfrage an den ersten Intro-Point schicken (über einen Tunnel).
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


async def send_rendezvous_over_tunnel(
    tunnel_client,
    request: RendezvousRequest,
) -> None:
    """
    Sendet eine Rendezvous-Anfrage über einen bestehenden Tunnel.

    Args:
        tunnel_client: Ein ErebosTunnelClient, der bereits mit dem Intro-Point
                       verbunden ist.
        request: Die Rendezvous-Anfrage.
    """
    payload = request.to_dict()
    await tunnel_client.send_rendezvous_request(payload)
    logger.info(f"Rendezvous-Request gesendet an {tunnel_client.peer_name}")


async def receive_rendezvous_response(tunnel_client) -> Optional[dict]:
    """
    Wartet auf eine Rendezvous-Antwort über den Tunnel.

    Args:
        tunnel_client: Ein ErebosTunnelClient, der mit dem Intro-Point verbunden ist.

    Returns:
        Die Antwort als dict, oder None bei Timeout.
    """
    try:
        raw = await asyncio.wait_for(tunnel_client.receive(), timeout=10.0)
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))
    except asyncio.TimeoutError:
        logger.error("Timeout beim Warten auf Rendezvous-Antwort")
        return None
