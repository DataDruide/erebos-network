"""Erebos-Router - Kernkomponente des Netzwerks.

Der Router entscheidet, welcher Sektor für welche Anfrage verwendet wird.
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from urllib.parse import urlparse

from .sectors import Sector, SectorType, get_sector

logger = logging.getLogger(__name__)


class RouteType(Enum):
    """Ziel-Typ für Routing-Entscheidung."""

    CLEARNET = "clearnet"
    EEPSITE = "eepsite"
    EREBOS_PEER = "erebos_peer"


@dataclass
class Route:
    """Eine Routing-Entscheidung."""

    target: str
    route_type: RouteType
    sector: Sector
    reason: str


class ErebosRouter:
    """Der Erebos-Router.

    Entscheidet, wie Traffic geroutet wird:
    - Clearnet -> Tor-Exit
    - eepSite -> I2P-Tunnel
    - Erebos-Peer -> Direkt

    Und mit welchem Sektor (Anonymitäts-Level).
    """

    def __init__(
        self,
        default_sector: SectorType = SectorType.STANDARD,
        tor_proxy: str = "127.0.0.1:9050",
        i2p_proxy: str = "127.0.0.1:4444",
    ):
        self.default_sector = default_sector
        self.tor_proxy = tor_proxy
        self.i2p_proxy = i2p_proxy
        self.stats = {
            "routes_total": 0,
            "routes_clearnet": 0,
            "routes_eepsite": 0,
            "routes_peer": 0,
        }

    def classify_target(self, target: str) -> RouteType:
        """Klassifiziert das Ziel.

        Args:
            target: URL oder Hostname

        Returns:
            RouteType (CLEARNET, EEPSITE, EREBOS_PEER)
        """
        if target.endswith(".i2p"):
            return RouteType.EEPSITE
        if target.endswith(".erebos"):
            return RouteType.EREBOS_PEER
        return RouteType.CLEARNET

    def select_sector(self, route_type: RouteType) -> Sector:
        """Wählt einen Sektor basierend auf Route-Typ.

        Clearnet -> Standard (schnell genug)
        eepSite -> Standard (I2P hat eigene Latenz)
        Peer -> Fast (intern, vertrauenswürdig)
        """
        if route_type == RouteType.EEPSITE:
            return get_sector(SectorType.STANDARD)
        if route_type == RouteType.EREBOS_PEER:
            return get_sector(SectorType.FAST)
        return get_sector(self.default_sector)

    def route(self, target: str, sector: Optional[SectorType] = None) -> Route:
        """Erstellt eine Routing-Entscheidung.

        Args:
            target: Ziel-URL oder Hostname
            sector: Optional - überschreibt den Standard-Sektor

        Returns:
            Route mit allen Details
        """
        route_type = self.classify_target(target)

        if sector is not None:
            selected_sector = get_sector(sector)
            reason = f"User-gewählter Sektor: {sector.value}"
        else:
            selected_sector = self.select_sector(route_type)
            reason = f"Auto-Sektor für {route_type.value}"

        route = Route(
            target=target,
            route_type=route_type,
            sector=selected_sector,
            reason=reason,
        )

        self.stats["routes_total"] += 1
        if route_type == RouteType.CLEARNET:
            self.stats["routes_clearnet"] += 1
        elif route_type == RouteType.EEPSITE:
            self.stats["routes_eepsite"] += 1
        else:
            self.stats["routes_peer"] += 1

        logger.info(
            f"Route: {target} -> {route_type.value} via {selected_sector.name}"
        )
        return route

    async def route_async(self, target: str, sector: Optional[SectorType] = None) -> Route:
        """Asynchrone Variante von route()."""
        await asyncio.sleep(0)
        return self.route(target, sector)

    def get_proxy_for(self, route: Route) -> Optional[str]:
        """Gibt den Proxy für eine Route zurück."""
        if route.route_type == RouteType.CLEARNET:
            return self.tor_proxy
        if route.route_type == RouteType.EEPSITE:
            return self.i2p_proxy
        return None

    def get_stats(self) -> dict:
        """Gibt Router-Statistiken zurück."""
        return dict(self.stats)
