"""Peer-Discovery für Erebos Network.

Findet Peers dezentral ohne zentralen Server.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .dht import (
    KBucket,
    PeerInfo,
    RoutingTable,
    common_prefix_length,
    generate_peer_id,
    xor_distance,
)

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryConfig:
    """Konfiguration für Peer-Discovery."""

    bootstrap_peers: list[str] = field(default_factory=list)
    max_peers: int = 1000
    refresh_interval_seconds: int = 300
    peer_timeout_seconds: int = 3600


class PeerDiscovery:
    """Peer-Discovery-Service.

    Findet Peers über DHT, Bootstrap-Nodes und Peer-Exchange.
    """

    def __init__(
        self,
        own_address: str,
        config: Optional[DiscoveryConfig] = None,
    ):
        self.own_address = own_address
        self.own_id = generate_peer_id(own_address)
        self.config = config or DiscoveryConfig()
        self.routing_table = RoutingTable(self.own_id)
        self._known_peers: dict[str, PeerInfo] = {}
        self.stats = {
            "peers_discovered": 0,
            "peers_added": 0,
            "peers_removed": 0,
            "lookups": 0,
        }

    @property
    def peer_count(self) -> int:
        """Anzahl bekannter Peers."""
        return self.routing_table.total_peers

    def add_peer(self, address: str, reputation: float = 0.5) -> bool:
        """Fügt einen Peer hinzu.

        Args:
            address: IP:Port
            reputation: Reputation (0.0-1.0)

        Returns:
            True wenn hinzugefügt
        """
        peer_id = generate_peer_id(address)
        if peer_id == self.own_id:
            return False

        peer = PeerInfo(
            peer_id=peer_id,
            address=address,
            reputation=reputation,
        )

        if self.routing_table.add_peer(peer):
            self._known_peers[peer_id] = peer
            self.stats["peers_added"] += 1
            return True
        return False

    def remove_peer(self, peer_id: str) -> bool:
        """Entfernt einen Peer."""
        if peer_id in self._known_peers:
            del self._known_peers[peer_id]
            self.routing_table.remove_peer(peer_id)
            self.stats["peers_removed"] += 1
            return True
        return False

    def lookup(self, target_id: str) -> list[PeerInfo]:
        """Sucht Peers nahe einer Ziel-ID.

        Args:
            target_id: Ziel-Peer-ID

        Returns:
            Liste der nächsten Peers
        """
        self.stats["lookups"] += 1
        return self.routing_table.find_closest(target_id)

    def bootstrap(self) -> int:
        """Bootstrappt über konfigurierte Peers.

        Returns:
            Anzahl hinzugefügter Peers
        """
        added = 0
        for address in self.config.bootstrap_peers:
            if self.add_peer(address):
                added += 1
                self.stats["peers_discovered"] += 1
        return added

    def cleanup_stale(self, max_age: float = 3600) -> int:
        """Entfernt veraltete Peers.

        Returns:
            Anzahl entfernter Peers
        """
        removed = 0
        for bucket in self.routing_table.buckets.values():
            for peer in bucket.get_stale(max_age):
                self.remove_peer(peer.peer_id)
                removed += 1
        return removed

    def get_stats(self) -> dict:
        """Gibt Statistiken zurück."""
        return {
            **self.stats,
            "peer_count": self.peer_count,
            "dht": self.routing_table.get_stats(),
        }
