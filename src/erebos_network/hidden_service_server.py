"""Server-Seite für Erebos-eigene Hidden Services."""

import asyncio
import logging
from typing import Optional

from .rendezvous import RendezvousRequest, RendezvousResponse

logger = logging.getLogger(__name__)


async def handle_rendezvous_request(
    request: RendezvousRequest,
    tunnel_factory,
) -> RendezvousResponse:
    """
    Verarbeitet eine Rendezvous-Anfrage auf der Hidden-Service-Seite.
    
    Ablauf:
    1. Rendezvous-Punkt aus der Anfrage extrahieren.
    2. Tunnel zum Rendezvous-Punkt aufbauen.
    3. Antwort an den Client zurückschicken.
    """
    logger.info(f"Rendezvous-Anfrage von Client (Key: {request.client_ephemeral_key.hex()[:16]}...)")
    logger.info(f"Rendezvous-Punkt: {request.rendezvous_peer_id} ({request.rendezvous_address})")
    
    try:
        tunnel = await tunnel_factory(request.rendezvous_address)
        logger.info(f"Tunnel zum Rendezvous-Punkt aufgebaut: {tunnel}")
        return RendezvousResponse(
            status="ok",
            message="Rendezvous-Tunnel aufgebaut",
            created_at=asyncio.get_event_loop().time(),
        )
    except Exception as e:
        logger.error(f"Fehler beim Tunnel-Aufbau: {e}")
        return RendezvousResponse(
            status="error",
            message=str(e),
            created_at=asyncio.get_event_loop().time(),
        )
