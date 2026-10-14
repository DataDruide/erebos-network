"""Erebos-Proxy - Lokaler HTTP-Proxy.

Nimmt Anfragen entgegen und leitet sie über den Erebos-Router.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from .router import ErebosRouter, RouteType
from .sectors import SectorType
from .tunnel import ErebosTunnelClient, FRAME_OPEN, FRAME_RELAY
from .onion import seal_for
from .augur_defense import AugurConfig, PredictivePerturbation, RateShaper

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


class ErebosSocks5Server:
    """SOCKS5-Listener mit direkter Weiterleitung.

    Nimmt SOCKS5-Verbindungen an, fragt den Erebos-Router nach der Route
    und leitet den Traffic direkt an das Ziel weiter. Dies ist die
    Uebergangsloesung, bis echtes Erebos-Routing implementiert ist.
    """

    def __init__(self, proxy, host="127.0.0.1", port=4447):
        self.proxy = proxy
        self.host = host
        self.port = port
        self._server = None
        self._connections = 0

        KEYS = Path(__file__).parent.parent.parent / "erebos_keys"
        self.peer1_pub = (KEYS / "peer1_x25519.pub").read_bytes()
        self.peer2_pub = (KEYS / "peer2_x25519.pub").read_bytes()
        self.peer3_pub = (KEYS / "peer3_x25519.pub").read_bytes()
        self.peer1_host = "127.0.0.1"
        self.peer1_port = 9999
        self.peer2_port = 9998
        self.peer3_port = 9997

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
            #   L3 (an Peer-3):  FRAME_OPEN + "host:port"
            #   L2 (an Peer-2):  FRAME_RELAY + hdr(OPEN, :9997) + L3
            #   L1 (an Peer-1):  FRAME_RELAY + hdr(RELAY, :9998) + L2
            # Der Transport-Tunnel zu Peer-1 (Port 9999) verschluesselt
            # L1 nochmal (ErebosTunnelClient.cipher).
            from .onion import (
                pack_relay_header,
                FRAME_OPEN_WIRE,
                FRAME_RELAY_WIRE,
            )

            target_bytes = f"{host}:{port}".encode()

            # l3-Klartext = "host:port" (kein Frame-Marker; der kommt per
            # send_typed(FRAME_OPEN, ...) auf Transport-Ebene durch Peer-2).
            l3_plain = target_bytes
            l3 = seal_for(self.peer3_pub, l3_plain)

            # l2-Klartext = hdr2 (3B) + l3-Sealed
            hdr2 = pack_relay_header(FRAME_OPEN_WIRE, self.peer3_port)
            l2_plain = hdr2 + l3
            l2 = seal_for(self.peer2_pub, l2_plain)

            # l1-Klartext = hdr1 (3B) + l2-Sealed
            hdr1 = pack_relay_header(FRAME_RELAY_WIRE, self.peer2_port)
            l1_plain = hdr1 + l2
            l1 = seal_for(self.peer1_pub, l1_plain)

            tunnel = ErebosTunnelClient(host=self.peer1_host, port=self.peer1_port)
            try:
                await asyncio.wait_for(tunnel.connect(), timeout=10.0)
            except Exception as e:
                logger.error(f"[{conn_id}] Tunnel-Aufbau fehlgeschlagen: {e}")
                await self._send_reply(writer, SOCKS5_REP_HOST_UNREACHABLE)
                writer.close()
                return

            await tunnel.send_typed(FRAME_RELAY, l1)
            await self._send_reply(writer, SOCKS5_REP_SUCCESS)
            logger.info(f"[{conn_id}] Tunnel steht, leite Traffic weiter")

            async def tunnel_to_client():
                while True:
                    data = await tunnel.receive()
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()

            async def client_to_tunnel():
                while True:
                    data = await reader.read(65536)
                    if not data:
                        break
                    await tunnel.send(data)

            await asyncio.gather(
                tunnel_to_client(), client_to_tunnel(), return_exceptions=True
            )
            await tunnel.close()
        except asyncio.IncompleteReadError:
            pass
        except Exception as e:
            logger.error(f"[{conn_id}] Fehler: {e}")
        finally:
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
