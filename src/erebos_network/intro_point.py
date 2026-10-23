"""Intro-Point-Logik für Erebos-eigene Hidden Services."""

import json
import logging
from typing import Optional

from .rendezvous import RendezvousRequest

logger = logging.getLogger(__name__)


async def forward_rendezvous_request(
    request_payload: dict,
    hidden_service_tunnel,
) -> None:
    """
    Leitet eine Rendezvous-Anfrage an den Hidden Service weiter.
    
    Args:
        request_payload: Die Rendezvous-Anfrage als dict.
        hidden_service_tunnel: Ein bestehender Tunnel zum Hidden Service.
    """
    logger.info(f"Leite Rendezvous-Anfrage an Hidden Service weiter (Rendezvous-Punkt: {request_payload.get('rendezvous_peer_id')})")
    payload = json.dumps(request_payload).encode("utf-8")
    await hidden_service_tunnel.send_rendezvous_request(request_payload)


async def receive_rendezvous_response_from_hs(
    hidden_service_tunnel,
) -> Optional[dict]:
    """
    Empfängt die Antwort vom Hidden Service und gibt sie zurück.
    """
    raw = await hidden_service_tunnel.receive()
    if not raw:
        return None
    return json.loads(raw.decode("utf-8"))
