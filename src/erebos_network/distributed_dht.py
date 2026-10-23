"""Verteilte DHT für Hidden-Service-Descriptors.

Nutzt die RoutingTable (Kademlia) zur Peer-Auswahl und verteilt
Descriptors über die nächsten Peers. Für den Moment ist die
Speicherung lokal (im RoutingTable-nahen Store), aber die
Schnittstelle ist so gestaltet, dass später echte Netzwerk-Puts
und -Gets möglich sind.
"""

import hashlib
from typing import Optional

from .dht import RoutingTable, PeerInfo


class DistributedDescriptorStore:
    """Verteilte DHT für Hidden-Service-Descriptors."""

    def __init__(self, own_id: str):
        self.own_id = own_id
        self.routing_table = RoutingTable(own_id)
        self._local_store = {}

    def put(self, key: bytes, value: dict) -> None:
        """Speichert einen Descriptor lokal und (später) bei den nächsten Peers."""
        self._local_store[key] = value
        # TODO: Verteile an die nächsten Peers (Kademlia-Put)
        # Für den Moment: nur lokal.

    def get(self, key: bytes) -> Optional[dict]:
        """Holt einen Descriptor (lokal oder von Peers)."""
        # 1. Lokal prüfen
        if key in self._local_store:
            return self._local_store[key]

        # 2. Bei den nächsten Peers anfragen (TODO: echte Netzwerk-Get)
        # Für den Moment: None.
        return None

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
