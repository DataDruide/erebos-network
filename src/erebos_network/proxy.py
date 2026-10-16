"""Erebos-Proxy - Lokaler HTTP-Proxy.

Nimmt Anfragen entgegen und leitet sie über den Erebos-Router.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .router import ErebosRouter, RouteType
from .sectors import SectorType
from .tunnel import ErebosTunnelClient, FRAME_OPEN, FRAME_RELAY, FRAME_COVER
from .cover import CoverConfig, TunnelCoverInjector
from .onion import seal_for
from .augur_defense import AugurConfig, PredictivePerturbation, RateShaper
from .topology_utils import select_three_hops

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
        traffic_shaping: bool = False,
        target_rate: float = 10.0,
        jitter_ratio: float = 0.3,
    ):
        self.router = router or ErebosRouter()
        self.host = host
        self.port = port
        self._running = False
        # Traffic-Shaping ist Opt-In (Default: aus, um Tests nicht zu brechen).
        self.shaper = (
            RateShaper(
                target_rate_per_second=target_rate,
                jitter_enabled=True,
                jitter_ratio=jitter_ratio,
            )
            if traffic_shaping
            else None
        )
        self._stats = {
            "requests_total": 0,
            "requests_routed": 0,
            "requests_failed": 0,
            "shaped_requests": 0,
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

        # Traffic-Shaping (nur wenn aktiviert)
        if self.shaper is not None:
            if not self.shaper.allow():
                delay = self.shaper.delay_for_next()
                if delay > 0:
                    await asyncio.sleep(delay)
                    self._stats["shaped_requests"] += 1

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
            "traffic_shaping": self.shaper is not None,
            "shaper": self.shaper.get_stats() if self.shaper else None,
            "router": self.router.get_stats(),
        }


# ---------------------------------------------------------------------------
# SOCKS5-Listener (vollstaendig, mit direkter Weiterleitung)
# ---------------------------------------------------------------------------

SOCKS5_VERSION = 0x05
SOCKS5_NO_AUTH = 0x00
SOCKS5_CMD_CONNECT = 0x01
SOCKS5_ATYP_IPV4 = 0x01
SOCKS5_ATYP_DOMAIN = 0x03
SOCKS5_ATYP_IPV6 = 0x04
SOCKS5_REP_SUCCESS = 0x00
SOCKS5_REP_GENERAL_FAILURE = 0x01
SOCKS5_REP_HOST_UNREACHABLE = 0x04
SOCKS5_REP_CMD_NOT_SUPPORTED = 0x07


@dataclass
class Socks5Config:
    """Konfiguration für den 3-Hop-SOCKS5-Listener.

    Erlaubt es, Pfade, Ports und Peer-Namen ohne Code-Änderung anzupassen.
    Defaults sind mit den bisherigen Hardcoded-Werten identisch, damit
    bestehende Aufrufe unverändert funktionieren.
    """

    keys_dir: Path = field(default_factory=lambda: Path("erebos_keys"))
    entry_host: str = "127.0.0.1"
    entry_port: int = 9999
    relay1_port: int = 9998
    relay2_port: int = 9997
    # Peer-Pool für die 3-Hop-Auswahl.
    # Default = alte hardcoded Peers (Backward-Compat).
    peer_pool: list[str] = field(
        default_factory=lambda: ["peer1", "peer2", "peer3"]
    )
    # Wie werden die 3 Hops aus dem Pool gewählt?
    #   "random"      -> random.sample(pool, 3)  (DEFAULT, SPOF-Vermeidung)
    #   "first"       -> pool[0], pool[1], pool[2]  (deterministisch, SPOF)
    #   "round_robin" -> rotierend bei jeder Verbindung
    #
    # Hinweis: Default ist "random", um Single-Point-of-Failure zu vermeiden.
    # Wer deterministisches Verhalten braucht, setzt entry_strategy="first"
    # explizit.
    entry_strategy: str = "random"
    connect_timeout: float = 10.0
    max_chunk: int = 65536
    # Timing-Obfuskation auf dem Byte-Stream (opt-in)
    traffic_shaping: bool = False
    target_rate: float = 10.0
    jitter_ratio: float = 0.3

    def peer_pub_path(self, peer_name: str) -> Path:
        """Pfad zum X25519-Public-Key eines Peers."""
        return self.keys_dir / f"{peer_name}_x25519.pub"

    # --- Backward-Compat: alte Namen als Properties ---

    @property
    def peer1_name(self) -> str:
        return self.peer_pool[0] if len(self.peer_pool) > 0 else "peer1"

    @property
    def peer2_name(self) -> str:
        return self.peer_pool[1] if len(self.peer_pool) > 1 else "peer2"

    @property
    def peer3_name(self) -> str:
        return self.peer_pool[2] if len(self.peer_pool) > 2 else "peer3"


class ErebosSocks5Server:
    """SOCKS5-Listener mit direkter Weiterleitung.

    Nimmt SOCKS5-Verbindungen an, fragt den Erebos-Router nach der Route
    und leitet den Traffic direkt an das Ziel weiter. Dies ist die
    Uebergangsloesung, bis echtes Erebos-Routing implementiert ist.
    """

    def __init__(
        self,
        proxy,
        host: str = "127.0.0.1",
        port: int = 4447,
        config: Optional[Socks5Config] = None,
        anonymity_provider=None,
    ):
        self.proxy = proxy
        self.host = host
        self.port = port
        self.config = config or Socks5Config()
        # Anonymitaets-Provider: Default = len(peer_pool) als Proxy
        # fuer die Netzwerkgroesse (der Proxy kennt nur seine Hop-Kandidaten).
        if anonymity_provider is None:
            self._anonymity_provider = lambda: len(self.config.peer_pool)
        else:
            self._anonymity_provider = anonymity_provider
        self._server = None
        self._connections = 0
        # Offset für round_robin-Strategie
        self._rr_offset = 0
        # RateShaper für Timing-Obfuskation (opt-in via traffic_shaping=True)
        self.shaper = (
            RateShaper(
                target_rate_per_second=self.config.target_rate,
                jitter_enabled=True,
                jitter_ratio=self.config.jitter_ratio,
            )
            if self.config.traffic_shaping
            else None
        )
        self._load_peer_keys()

    def _load_peer_keys(self) -> None:
        """Lädt X25519-Public-Keys für ALLE Peers im Pool."""
        cfg = self.config
        if len(cfg.peer_pool) < 3:
            raise ValueError(
                f"peer_pool muss mindestens 3 Peers haben, hat {len(cfg.peer_pool)}"
            )
        # Alle Pool-Peers laden
        self.peer_pubs: dict[str, bytes] = {}
        for name in cfg.peer_pool:
            self.peer_pubs[name] = cfg.peer_pub_path(name).read_bytes()
        # Ports: Entry + 2 Relays (nach Pool-Reihenfolge)
        self.peer_ports: dict[str, int] = {}
        for i, name in enumerate(cfg.peer_pool):
            if i == 0:
                self.peer_ports[name] = cfg.entry_port
            elif i == 1:
                self.peer_ports[name] = cfg.relay1_port
            else:
                self.peer_ports[name] = cfg.relay2_port
        self.entry_host = cfg.entry_host

    def _select_three_hops(self) -> list[str]:
        """Wählt 3 Peers aus dem Pool (delegiert an freie Funktion)."""
        pool = self.config.peer_pool
        hops = select_three_hops(pool, self.config.entry_strategy, self._rr_offset)
        if self.config.entry_strategy == "round_robin" and len(pool) >= 3:
            self._rr_offset = (self._rr_offset + 1) % len(pool)
        return hops

    # --- Backward-Compat: alte Attribute als Properties ---

    @property
    def peer1_pub(self) -> bytes:
        return self.peer_pubs.get(self.config.peer1_name, b"")

    @property
    def peer2_pub(self) -> bytes:
        return self.peer_pubs.get(self.config.peer2_name, b"")

    @property
    def peer3_pub(self) -> bytes:
        return self.peer_pubs.get(self.config.peer3_name, b"")

    @property
    def peer1_host(self) -> str:
        return self.entry_host

    @property
    def peer1_port(self) -> int:
        return self.peer_ports.get(self.config.peer1_name, self.config.entry_port)

    @property
    def peer2_port(self) -> int:
        return self.peer_ports.get(self.config.peer2_name, self.config.relay1_port)

    @property
    def peer3_port(self) -> int:
        return self.peer_ports.get(self.config.peer3_name, self.config.relay2_port)

    async def start(self):
        self._server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        logger.info(f"Erebos SOCKS5-Proxy laeuft auf {self.host}:{self.port}")

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("Erebos SOCKS5-Proxy gestoppt")

    async def _handle_client(self, reader, writer):
        self._connections += 1
        conn_id = self._connections
        cover = None
        try:
            version = await reader.readexactly(1)
            if version[0] != SOCKS5_VERSION:
                writer.close()
                return

            nmethods = (await reader.readexactly(1))[0]
            methods = await reader.readexactly(nmethods)

            if SOCKS5_NO_AUTH not in methods:
                writer.write(bytes([SOCKS5_VERSION, 0xFF]))
                await writer.drain()
                writer.close()
                return

            writer.write(bytes([SOCKS5_VERSION, SOCKS5_NO_AUTH]))
            await writer.drain()

            request = await reader.readexactly(4)
            if request[0] != SOCKS5_VERSION:
                writer.close()
                return

            cmd = request[1]
            atyp = request[3]

            if cmd != SOCKS5_CMD_CONNECT:
                await self._send_reply(writer, SOCKS5_REP_CMD_NOT_SUPPORTED)
                writer.close()
                return

            if atyp == SOCKS5_ATYP_IPV4:
                raw = await reader.readexactly(4)
                host = ".".join(str(b) for b in raw)
            elif atyp == SOCKS5_ATYP_DOMAIN:
                length = (await reader.readexactly(1))[0]
                raw = await reader.readexactly(length)
                host = raw.decode("ascii")
            elif atyp == SOCKS5_ATYP_IPV6:
                raw = await reader.readexactly(16)
                host = ":".join(
                    f"{raw[i]:02x}{raw[i+1]:02x}" for i in range(0, 16, 2)
                )
            else:
                await self._send_reply(writer, SOCKS5_REP_GENERAL_FAILURE)
                writer.close()
                return

            port = int.from_bytes(await reader.readexactly(2), "big")
            logger.info(f"[{conn_id}] SOCKS5 -> {host}:{port}")

            result = await self.proxy.handle_request(f"http://{host}:{port}")
            logger.info(
                f"[{conn_id}] Route: {result.get('sector')} "
                f"({result.get('hops')} Hops)"
            )

            # 3-Hop-Onion bauen:
            #   Hop-Auswahl per _select_three_hops() (peer_pool + entry_strategy)
            #   L3 (an Hop3): FRAME_OPEN + "host:port"
            #   L2 (an Hop2): FRAME_RELAY + hdr(OPEN, hop3_port) + L3
            #   L1 (an Hop1): FRAME_RELAY + hdr(RELAY, hop2_port) + L2
            # Der Transport-Tunnel zu Hop1 verschluesselt L1 nochmal.
            from .onion import (
                pack_relay_header,
                FRAME_OPEN_WIRE,
                FRAME_RELAY_WIRE,
            )

            hops = self._select_three_hops()
            hop1, hop2, hop3 = hops[0], hops[1], hops[2]
            hop1_pub = self.peer_pubs[hop1]
            hop2_pub = self.peer_pubs[hop2]
            hop3_pub = self.peer_pubs[hop3]
            hop1_port = self.peer_ports[hop1]
            hop2_port = self.peer_ports[hop2]
            hop3_port = self.peer_ports[hop3]
            logger.info(
                f"[{conn_id}] Pfad: {hop1}:{hop1_port} -> "
                f"{hop2}:{hop2_port} -> {hop3}:{hop3_port}"
            )

            target_bytes = f"{host}:{port}".encode()

            # l3-Klartext = "host:port"
            l3_plain = target_bytes
            l3 = seal_for(hop3_pub, l3_plain)

            # l2-Klartext = hdr2 (3B) + l3-Sealed
            hdr2 = pack_relay_header(FRAME_OPEN_WIRE, hop3_port)
            l2_plain = hdr2 + l3
            l2 = seal_for(hop2_pub, l2_plain)

            # l1-Klartext = hdr1 (3B) + l2-Sealed
            hdr1 = pack_relay_header(FRAME_RELAY_WIRE, hop2_port)
            l1_plain = hdr1 + l2
            l1 = seal_for(hop1_pub, l1_plain)

            tunnel = ErebosTunnelClient(host=self.entry_host, port=hop1_port)
            try:
                await asyncio.wait_for(tunnel.connect(), timeout=self.config.connect_timeout)
            except Exception as e:
                logger.error(f"[{conn_id}] Tunnel-Aufbau fehlgeschlagen: {e}")
                await self._send_reply(writer, SOCKS5_REP_HOST_UNREACHABLE)
                writer.close()
                return

            await tunnel.send_typed(FRAME_RELAY, l1)
            await self._send_reply(writer, SOCKS5_REP_SUCCESS)
            logger.info(f"[{conn_id}] Tunnel steht, leite Traffic weiter")

            # Cover-Traffic-Injector (P1.1b): sendet FRAME_COVER-Frames
            # im Burst-Modus, um Timing-Fingerprinting zu verwischen.
            cover = TunnelCoverInjector(
                tunnel,
                CoverConfig(
                    mode="burst",
                    burst_size=3,
                    burst_pause_seconds=2.0,
                    adaptive=True,
                    quiet_seconds_after_real=3.0,
                    quiet_rate_factor=0.2,
                    boost_when_idle_seconds=10.0,
                    boost_factor=2.0,
                    anonymity_threshold=10,
                ),
                anonymity_provider=self._anonymity_provider,
            )
            await cover.start()

            async def tunnel_to_client():
                while True:
                    data = await tunnel.receive()
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()

            async def client_to_tunnel():
                while True:
                    data = await reader.read(self.config.max_chunk)
                    if not data:
                        break
                    # Timing-Obfuskation (opt-in): verzoegert Send bei Burst
                    if self.shaper is not None and not self.shaper.allow():
                        delay = self.shaper.delay_for_next()
                        if delay > 0:
                            await asyncio.sleep(delay)
                    await tunnel.send(data)
                    # Adaptiver Cover-Traffic: echten Traffic melden
                    if cover is not None:
                        cover.notify_real_traffic()

            await asyncio.gather(
                tunnel_to_client(), client_to_tunnel(), return_exceptions=True
            )
            if cover is not None:
                await cover.stop()
            await tunnel.close()
        except asyncio.IncompleteReadError:
            pass
        except Exception as e:
            logger.error(f"[{conn_id}] Fehler: {e}")
        finally:
            if cover is not None:
                try:
                    await cover.stop()
                except Exception:
                    pass
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _pipe(self, reader, writer):
        try:
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def _send_reply(self, writer, rep_code):
        reply = bytes([SOCKS5_VERSION, rep_code, 0x00, SOCKS5_ATYP_IPV4])
        reply += bytes([0, 0, 0, 0, 0, 0])
        writer.write(reply)
        await writer.drain()
