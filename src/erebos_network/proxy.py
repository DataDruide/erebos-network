"""Erebos-Proxy - Lokaler HTTP-Proxy.

Nimmt Anfragen entgegen und leitet sie über den Erebos-Router.
"""

import asyncio
import logging
from typing import Optional

from .router import ErebosRouter, RouteType
from .sectors import SectorType

logger = logging.getLogger(__name__)


class ErebosProxy:
    """Lokaler Proxy-Server.

    Lauscht auf einem Port und leitet Anfragen
    über den Erebos-Router weiter.
    """

    def __init__(
        self,
        router: Optional[ErebosRouter] = None,
        host: str = "127.0.0.1",
        port: int = 9050,
    ):
        self.router = router or ErebosRouter()
        self.host = host
        self.port = port
        self._running = False
        self._stats = {
            "requests_total": 0,
            "requests_routed": 0,
            "requests_failed": 0,
        }

    async def start(self) -> None:
        """Startet den Proxy (Simulation)."""
        self._running = True
        logger.info(f"Erebos-Proxy gestartet auf {self.host}:{self.port}")
        logger.info(f"Router: {self.router.default_sector.value} Sektor")

    async def stop(self) -> None:
        """Stoppt den Proxy."""
        self._running = False
        logger.info("Erebos-Proxy gestoppt")

    async def handle_request(
        self, target: str, sector: Optional[SectorType] = None
    ) -> dict:
        """Behandelt eine Anfrage.

        Args:
            target: Ziel-URL
            sector: Optional - Sektor-Override

        Returns:
            Antwort-Dict
        """
        self._stats["requests_total"] += 1

        try:
            route = await self.router.route_async(target, sector)
            proxy = self.router.get_proxy_for(route)

            await asyncio.sleep(0.01)  # Simulation Netzwerk-Latenz

            self._stats["requests_routed"] += 1

            return {
                "success": True,
                "target": target,
                "route_type": route.route_type.value,
                "sector": route.sector.name,
                "hops": route.sector.hops,
                "proxy": proxy,
                "reason": route.reason,
            }
        except Exception as e:
            self._stats["requests_failed"] += 1
            logger.error(f"Fehler bei {target}: {e}")
            return {
                "success": False,
                "target": target,
                "error": str(e),
            }

    def get_stats(self) -> dict:
        """Gibt Proxy-Statistiken zurück."""
        return {
            **self._stats,
            "running": self._running,
            "router": self.router.get_stats(),
        }
