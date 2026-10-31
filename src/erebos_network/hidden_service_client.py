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
    dht=None,
    rendezvous_peer_id: str = "",
    rendezvous_address: str = "",
    client_ephemeral_key: bytes = b"",
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

    # 1. Descriptor holen (über DHT_GET an Peers)
    descriptor = None

    if use_network:
        # DHT_GET direkt an Peers senden
        import hashlib as _hashlib
        import json as _json
        from .tunnel import ErebosTunnelClient, FRAME_DHT_GET
        from .peers_loader import load_peers

        key_hex = _hashlib.sha256(address.encode()).hexdigest()
        payload = _json.dumps({"key": key_hex}).encode("utf-8")

        for peer in load_peers():
            try:
                _host, _port_str = peer.address.split(":")
                _port = int(_port_str)
                client = ErebosTunnelClient(host=_host, port=_port)
                await client.connect()
                await client.send_typed(FRAME_DHT_GET, payload)
                response_raw = await asyncio.wait_for(client.receive(), timeout=5.0)
                await client.close()
                if response_raw:
                    response = _json.loads(response_raw.decode("utf-8"))
                    if response.get("value"):
                        descriptor = HiddenServiceDescriptor.from_dict(response["value"])
                        logger.info(f"DHT_GET von {peer.name}: Descriptor gefunden")
                        break
            except Exception as e:
                logger.warning(f"DHT_GET von {peer.name} fehlgeschlagen: {e}")
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
    # Descriptor am Request haengen, damit der Aufrufer ihn
    # wiederverwenden kann (statt ihn erneut aus der DHT zu holen).
    request.descriptor = descriptor

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
