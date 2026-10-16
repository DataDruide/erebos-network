"""HTTP-API-Server für Erebos Network.

Beantwortet Anfragen vom Browser:
- GET /status     - Ist der Server erreichbar?
- GET /route      - Routing-Entscheidung
- GET /resolve    - .erebos-Domain auflösen
- GET /stats      - Statistiken
"""

import json
import time
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from .discovery import PeerDiscovery
from .naming import NamingService
from .reputation import ReputationSystem
from .governance import Governance
from .router import ErebosRouter
from .sectors import SectorType
from .padding import pad_message
from .delay import DelayConfig
from .cover import ConstantCoverTraffic, CoverConfig
from .mixnet import get_mixnet_config
from .crypto.hybrid_kem import HybridKEM

logger = logging.getLogger(__name__)


class ErebosAPIHandler(BaseHTTPRequestHandler):
    """HTTP-Request-Handler für die Erebos-API."""

    # Gemeinsame Instanzen (in Produktion: Dependency Injection)
    router = ErebosRouter()
    discovery = PeerDiscovery("127.0.0.1:9050")
    naming = NamingService()
    reputation = ReputationSystem()
    governance = Governance()

    # Traffic-Härtung (Thema 1)
    _cover_traffic = None
    _hybrid_kem_sizes = None

    # Traffic-Härtung (Thema 1)
    _padding_block = 256
    _delay_cfg = DelayConfig(min_ms=0, max_ms=30, distribution="uniform")

    def _send_json(self, data: dict, status: int = 200) -> None:
        """Sendet JSON-Antwort mit Bucket-Padding + Timing-Jitter.

        Padding erfolgt als trailing whitespace INNERHALB des JSON-Strings —
        JSON-Parser ignorieren das, aber die Paketgroesse ist trotzdem
        auf Bucket-Grenzen normalisiert. So bleibt der Body valide UTF-8.
        """
        body = json.dumps(data).encode()
        original_size = len(body)

        # Naechste Bucket-Grenze
        block = self._padding_block
        target_size = ((original_size // block) + 1) * block
        padding_len = target_size - original_size

        # Whitespace-Padding (JSON-kompatibel)
        padded = body + (b" " * padding_len)

        # Timing-Jitter (max 30 ms — UI-tauglich)
        time.sleep(self._delay_cfg.sample())

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("X-Erebos-Original-Size", str(original_size))
        self.send_header("X-Erebos-Padded-Size", str(target_size))
        self.end_headers()
        self.wfile.write(padded)

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
        elif path == "/api/community/members":
            self._handle_community_members()
        elif path == "/api/community/governance":
            self._handle_community_governance()
        elif path == "/api/network/traffic-stats":
            self._handle_traffic_stats()
        elif path == "/api/network/pqc-status":
            self._handle_pqc_status()
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

    def _handle_community_members(self) -> None:
        """Community-Endpoint: Liste aller Peers mit Reputation."""
        peers = self.discovery.list_all_peers()
        reps = {r.peer_id: r for r in self.reputation.list_all()}

        members = []
        for peer in peers[:50]:  # Limit 50
            rep = reps.get(peer.peer_id)
            members.append({
                "peer_id": peer.peer_id[:16],
                "full_id": peer.peer_id,
                "address": peer.address,
                "reputation": round(rep.score if rep else peer.reputation, 2),
                "is_trusted": bool(rep and rep.score >= 0.7),
                "is_online": peer.is_online,
                "last_seen": int(peer.last_seen),
            })

        self._send_json({
            "success": True,
            "count": len(members),
            "members": members,
        })

    def _handle_community_governance(self) -> None:
        """Community-Endpoint: Governance-Proposals."""
        proposals = self.governance.list_all()
        self._send_json({
            "success": True,
            "count": len(proposals),
            "proposals": proposals,
        })

    def _handle_traffic_stats(self) -> None:
        """Aggregierte Traffic-Haertungs-Statistiken."""
        stats = {
            "padding": {
                "block_size": self._padding_block,
                "active": True,
            },
            "delay": {
                "min_ms": self._delay_cfg.min_ms,
                "max_ms": self._delay_cfg.max_ms,
                "distribution": self._delay_cfg.distribution,
            },
            "cover": (
                self._cover_traffic.get_stats()
                if self._cover_traffic is not None
                else {"running": False, "messages_sent": 0, "bytes_sent": 0}
            ),
            "mixnet": self._mixnet_config_dict(),
        }
        self._send_json({"success": True, "traffic": stats})

    @staticmethod
    def _mixnet_config_dict() -> dict:
        """MixnetConfig als JSON-serialisierbares Dict."""
        cfg = get_mixnet_config("standard")
        out = {}
        for key, val in vars(cfg).items():
            if isinstance(val, (str, int, float, bool, type(None))):
                out[key] = val
            elif isinstance(val, (list, tuple)):
                out[key] = [
                    v if isinstance(v, (str, int, float, bool, type(None)))
                    else repr(v)
                    for v in val
                ]
            elif hasattr(val, "__dict__"):
                # verschachtelte Dataclass (z.B. DelayConfig)
                out[key] = {
                    k: v for k, v in vars(val).items()
                    if isinstance(v, (str, int, float, bool, type(None)))
                }
            else:
                out[key] = repr(val)
        return out

    def _handle_pqc_status(self) -> None:
        """Aktive Hybrid-PQC-Konfiguration."""
        self._send_json({
            "success": True,
            "pqc": HybridKEM.sizes(),
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
    logger.info("Endpoints: /status, /route, /resolve, /stats, /api/community/members, /api/community/governance, /api/network/traffic-stats, /api/network/pqc-status")

    # Cover-Traffic in Daemon-Thread starten (async-Loop)
    import threading
    import asyncio

    cover = ConstantCoverTraffic(CoverConfig())
    ErebosAPIHandler._cover_traffic = cover

    def _cover_runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(cover.start())
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
        finally:
            loop.close()

    cover_thread = threading.Thread(target=_cover_runner, daemon=True, name="erebos-cover")
    cover_thread.start()
    logger.info("Cover-Traffic-Thread gestartet")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Server gestoppt")
        server.shutdown()
