"""Peer-Modul für Erebos Network.

Repräsentiert einen Peer im Netzwerk.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .dht import generate_peer_id
from .discovery import DiscoveryConfig, PeerDiscovery
from .naming import NamingService

logger = logging.getLogger(__name__)


@dataclass
class PeerConfig:
    """Konfiguration für einen Erebos-Peer."""

    address: str
    bootstrap_peers: list[str] = field(default_factory=list)
    enable_discovery: bool = True
    enable_naming: bool = True


class ErebosPeer:
    """Ein Erebos-Peer.

    Kombiniert Discovery, Naming und Routing.
    """

    def __init__(self, config: PeerConfig):
        self.config = config
        self.address = config.address
        self.peer_id = generate_peer_id(config.address)

        self.discovery = PeerDiscovery(
            own_address=config.address,
            config=DiscoveryConfig(
                bootstrap_peers=config.bootstrap_peers,
            ),
        )
        self.naming = NamingService() if config.enable_naming else None
        self._running = False
        self._started_at: Optional[float] = None

    async def start(self) -> None:
        """Startet den Peer."""
        if self._running:
            return

        self._running = True
        self._started_at = time.time()

        if self.config.enable_discovery:
            added = self.discovery.bootstrap()
            logger.info(f"Bootstrap: {added} Peers hinzugefügt")

        logger.info(f"Peer gestartet: {self.peer_id[:16]}...")

    async def stop(self) -> None:
        """Stoppt den Peer."""
        self._running = False
        logger.info("Peer gestoppt")

    @property
    def uptime_seconds(self) -> float:
        """Uptime in Sekunden."""
        if self._started_at is None:
            return 0.0
        return time.time() - self._started_at

    def register_domain(self, name: str) -> Optional[str]:
        """Registriert eine .erebos-Domain für diesen Peer."""
        if self.naming is None:
            return None
        record = self.naming.register(name=name, address=self.address)
        return record.full_domain

    def resolve_domain(self, name: str) -> Optional[str]:
        """Löst eine .erebos-Domain auf."""
        if self.naming is None:
            return None
        record = self.naming.resolve(name)
        if record:
            return record.address
        return None

    def get_stats(self) -> dict:
        """Gibt Peer-Statistiken zurück."""
        return {
            "peer_id": self.peer_id[:16] + "...",
            "address": self.address,
            "running": self._running,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "discovery": self.discovery.get_stats(),
            "naming": self.naming.get_stats() if self.naming else None,
        }
