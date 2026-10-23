"""Verteilte DHT für Hidden-Service-Descriptors.

Nutzt die RoutingTable (Kademlia) zur Peer-Auswahl und verteilt
Descriptors über die nächsten Peers. Die Netzwerkkommunikation
läuft über ErebosTunnelClient.
"""

import asyncio
import hashlib
import json
import logging
from typing import Optional

from .dht import RoutingTable, PeerInfo, xor_distance

logger = logging.getLogger(__name__)


class DistributedDescriptorStore:
    """Verteilte DHT für Hidden-Service-Descriptors."""

    def __init__(self, own_id: str):
        self.own_id = own_id
        self.routing_table = RoutingTable(own_id)
        self._local_store = {}

    def put(self, key: bytes, value: dict) -> None:
        """Speichert einen Descriptor lokal und bei den nächsten Peers."""
        self._local_store[key] = value
        # Asynchron an die nächsten Peers verteilen (Fire-and-Forget)
        # In einer echten Implementierung würde man auf Bestätigungen warten.
        asyncio.create_task(self._distribute_put(key, value))

    def get(self, key: bytes) -> Optional[dict]:
        """Holt einen Descriptor (lokal oder von Peers)."""
        # 1. Lokal prüfen
        if key in self._local_store:
            return self._local_store[key]
        # 2. Bei den nächsten Peers anfragen (synchron, mit Timeout)
        # In einer echten Implementierung wäre das asynchron.
        # Für den Moment: None.
        return None

    async def _distribute_put(self, key: bytes, value: dict) -> None:
        """Verteilt einen Descriptor an die nächsten Peers."""
        target_id = key.hex()
        closest = self.routing_table.find_closest(target_id, count=3)
        for peer in closest:
            try:
                from .tunnel import ErebosTunnelClient
                host, port = peer.address.split(":")
                client = ErebosTunnelClient(host=host, port=int(port))
                await client.connect()
                # Sende einen speziellen Frame für DHT-Put
                # (Für den Moment: als Rendezvous-Request missbrauchen)
                payload = json.dumps({
                    "type": "dht_put",
                    "key": key.hex(),
                    "value": value,
                }).encode("utf-8")
                # TODO: Eigenen Frame-Typ für DHT-Put einführen
                logger.info(f"DHT-Put an {peer.address} (TODO: Frame-Typ)")
                await client.close()
            except Exception as e:
                logger.error(f"DHT-Put an {peer.address} fehlgeschlagen: {e}")

    def add_peer(self, peer: PeerInfo) -> bool:
        """Fügt einen Peer zur Routing-Tabelle hinzu."""
        return self.routing_table.add_peer(peer)

    def remove_peer(self, peer_id: str) -> bool:
        """Entfernt einen Peer aus der Routing-Tabelle."""
        return self.routing_table.remove_peer(peer_id)

    @property
    def size(self) -> int:
        """Anzahl der lokal gespeicherten Descriptors."""
        return len(self._local_store)

    @property
    def peer_count(self) -> int:
        """Anzahl der Peers in der Routing-Tabelle."""
        return self.routing_table.total_peers
