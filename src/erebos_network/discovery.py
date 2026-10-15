"""Peer-Discovery fuer Erebos Network.

Findet Peers dezentral ohne zentralen Server.
Erweitert um Eclipse-Schutz.
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
from .eclipse_protection import EclipseProtection

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryConfig:
    """Konfiguration fuer Peer-Discovery."""

    bootstrap_peers: list[str] = field(default_factory=list)
    max_peers: int = 1000
    refresh_interval_seconds: int = 300
    peer_timeout_seconds: int = 3600
    eclipse_protection: bool = True


class PeerDiscovery:
    """Peer-Discovery-Service.

    Findet Peers ueber DHT, Bootstrap-Nodes und Peer-Exchange.
    Mit Eclipse-Schutz durch Subnetz-Diversity.
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
        self.eclipse = (
            EclipseProtection()
            if self.config.eclipse_protection
            else None
        )
        self.stats = {
            "peers_discovered": 0,
            "peers_added": 0,
            "peers_removed": 0,
            "peers_rejected_eclipse": 0,
            "lookups": 0,
        }

    @property
    def peer_count(self) -> int:
        return self.routing_table.total_peers

    def add_peer(self, address: str, reputation: float = 0.5) -> bool:
        """Fuegt einen Peer hinzu (mit Eclipse-Schutz)."""
        peer_id = generate_peer_id(address)
        if peer_id == self.own_id:
            return False

        # Eclipse-Schutz
        if self.eclipse and not self.eclipse.can_accept(address):
            self.stats["peers_rejected_eclipse"] += 1
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
            peer = self._known_peers[peer_id]
            if self.eclipse:
                self.eclipse.remove(peer.address)
            del self._known_peers[peer_id]
            self.routing_table.remove_peer(peer_id)
            self.stats["peers_removed"] += 1
            return True
        return False

    def list_all_peers(self) -> list[PeerInfo]:
        """Gibt alle bekannten Peers zurueck (sortiert nach Reputation).

        Fuer Community-Endpoints: Liste aller Peers mit ihren Metadaten.
        """
        peers = list(self._known_peers.values())
        peers.sort(key=lambda p: p.reputation, reverse=True)
        return peers

    def lookup(self, target_id: str) -> list[PeerInfo]:
        """Sucht Peers nahe einer Ziel-ID."""
        self.stats["lookups"] += 1
        return self.routing_table.find_closest(target_id)

    def bootstrap(self) -> int:
        """Bootstrappt ueber konfigurierte Peers."""
        added = 0
        for address in self.config.bootstrap_peers:
            if self.add_peer(address):
                added += 1
                self.stats["peers_discovered"] += 1
        return added

    def cleanup_stale(self, max_age: float = 3600) -> int:
        """Entfernt veraltete Peers."""
        removed = 0
        for bucket in self.routing_table.buckets.values():
            for peer in bucket.get_stale(max_age):
                self.remove_peer(peer.peer_id)
                removed += 1
        return removed

    def export_topology(self, use_addresses: bool = False) -> list[tuple[str, str]]:
        """Exportiert die aktuelle Peer-Topologie als Kantenliste.

        Args:
            use_addresses: True  -> IP:Port als Knoten-IDs
                           False -> Peer-IDs (Hex)

        Returns:
            Liste von (own_key, peer_key) Paaren.
        """
        return self.routing_table.to_edges(use_addresses=use_addresses)

    def get_stats(self) -> dict:
        """Statistiken."""
        result = {
            **self.stats,
            "peer_count": self.peer_count,
            "dht": self.routing_table.get_stats(),
        }
        if self.eclipse:
            result["eclipse"] = self.eclipse.get_stats()
        return result
