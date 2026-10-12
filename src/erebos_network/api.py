"""HTTP-API-Server für Erebos Network.

Beantwortet Anfragen vom Browser:
- GET /status     - Ist der Server erreichbar?
- GET /route      - Routing-Entscheidung
- GET /resolve    - .erebos-Domain auflösen
- GET /stats      - Statistiken
"""

import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from .discovery import PeerDiscovery
from .naming import NamingService
from .router import ErebosRouter
from .sectors import SectorType

logger = logging.getLogger(__name__)


class ErebosAPIHandler(BaseHTTPRequestHandler):
    """HTTP-Request-Handler für die Erebos-API."""

    # Gemeinsame Instanzen (in Produktion: Dependency Injection)
    router = ErebosRouter()
    discovery = PeerDiscovery("127.0.0.1:9050")
    naming = NamingService()

    def _send_json(self, data: dict, status: int = 200) -> None:
        """Sendet JSON-Antwort."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self) -> None:
        """CORS-Preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """GET-Anfrage bearbeiten."""
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path == "/status":
            self._handle_status()
        elif path == "/route":
            self._handle_route(params)
        elif path == "/resolve":
            self._handle_resolve(params)
        elif path == "/stats":
            self._handle_stats()
        else:
            self._send_json({"error": "Not found"}, 404)

    def _handle_status(self) -> None:
        """Status-Endpoint."""
        self._send_json({
            "status": "ok",
            "service": "erebos-network",
            "version": "0.1.0",
        })

    def _handle_route(self, params: dict) -> None:
        """Routing-Endpoint."""
        target = params.get("target", [""])[0]
        sector_name = params.get("sector", [None])[0]

        if not target:
            self._send_json({"error": "target required"}, 400)
            return

        sector = None
        if sector_name:
            try:
                sector = SectorType(sector_name)
            except ValueError:
                pass

        route = self.router.route(target, sector)
        proxy = self.router.get_proxy_for(route)

        self._send_json({
            "success": True,
            "target": target,
            "route_type": route.route_type.value,
            "sector": route.sector.name,
            "hops": route.sector.hops,
            "proxy": proxy,
            "reason": route.reason,
        })

    def _handle_resolve(self, params: dict) -> None:
        """Domain-Auflösung."""
        name = params.get("name", [""])[0]
        if not name:
            self._send_json({"error": "name required"}, 400)
            return

        record = self.naming.resolve(name)
        if record:
            self._send_json({
                "success": True,
                "name": name,
                "address": record.address,
                "peer_id": record.peer_id[:16] + "...",
            })
        else:
            self._send_json({
                "success": False,
                "name": name,
                "error": "not found",
            }, 404)

    def _handle_stats(self) -> None:
        """Statistik-Endpoint."""
        self._send_json({
            "success": True,
            "router": self.router.get_stats(),
            "discovery": self.discovery.get_stats(),
            "naming": self.naming.get_stats(),
            "default_sector": self.router.default_sector.value,
        })

    def log_message(self, format, *args) -> None:
        """Unterdrückt Standard-Logging."""
        logger.debug(format, *args)


def run_server(host: str = "127.0.0.1", port: int = 9050) -> None:
    """Startet den API-Server.

    Args:
        host: Bind-Adresse
        port: Port (Standard: 9050)
    """
    server = HTTPServer((host, port), ErebosAPIHandler)
    logger.info(f"Erebos API Server gestartet auf http://{host}:{port}")
    logger.info("Endpoints: /status, /route, /resolve, /stats")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server gestoppt")
        server.shutdown()
