"""Erebos-Proxy - Lokaler HTTP-Proxy.

Nimmt Anfragen entgegen und leitet sie über den Erebos-Router.
"""

import json
import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .router import ErebosRouter, RouteType
from .sectors import SectorType
from .tunnel import ErebosTunnelClient, FRAME_OPEN, FRAME_RELAY, FRAME_COVER, FRAME_DATA
from .cover import CoverConfig, TunnelCoverInjector
from .onion import seal_for
from .augur_defense import AugurConfig, PredictivePerturbation, RateShaper
from .topology_utils import select_three_hops

logger = logging.getLogger(__name__)


def _peer_name_to_port(peer_name: str) -> int:
    """Leitet den Port aus dem Peer-Namen ab (z. B. peer1 -> 9999)."""
    mapping = {"peer1": 9999, "peer2": 9998, "peer3": 9997}
    return mapping.get(peer_name, 9999)


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
        cover_profile: Optional[str] = None,
        auto_profile: bool = False,
    ):
        self.proxy = proxy
        self.host = host
        self.port = port
        self.config = config or Socks5Config()
        self._cover_profile = cover_profile
        self._auto_profile = auto_profile
        if auto_profile:
            from .cover import CoverProfileDetector
            self._profile_detector = CoverProfileDetector()
        else:
            self._profile_detector = None
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
        # conn_id waechst monoton; bei 65000 zuruecksetzen, damit
        # stream_id = conn_id & 0xFFFF nicht ueberlaeuft (65535).
        if self._connections >= 65000:
            self._connections = 1
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

            # Prüfe, ob es eine .erebos-Adresse ist
            if host.endswith(".erebos"):
                logger.info(f"[{conn_id}] .erebos-Adresse erkannt: {host}")
                from .hidden_service_client import connect_to_hidden_service
                from .descriptor_store import DescriptorStore
                import os
                
                # Verteilte DHT (Kademlia-basiert)
                from .distributed_dht import DistributedDescriptorStore
                from .dht import PeerInfo
                dht = getattr(self, "_descriptor_store", None)
                if dht is None:
                    own_id = "00" * 32
                    dht = DistributedDescriptorStore(own_id)
                    # Peers aus der Config eintragen
                    for i, (peer_name, peer_pub) in enumerate(self.peer_pubs.items()):
                        # Peer-ID aus dem Namen ableiten (vereinfacht)
                        peer_id = f"{i:02x}" * 32
                        # Adresse aus dem Peer-Namen ableiten (Port-Mapping)
                        port = 9997 + i  # peer1 -> 9997, peer2 -> 9998, ...
                        peer_info = PeerInfo(
                            peer_id=peer_id,
                            address=f"127.0.0.1:{port}",
                        )
                        dht.add_peer(peer_info)
                    self._descriptor_store = dht
                
                # Rendezvous-Punkt wählen (vereinfacht: erster Peer)
                rendezvous_peer = list(self.peer_pubs.keys())[0] if self.peer_pubs else None
                if rendezvous_peer is None:
                    logger.error(f"[{conn_id}] Kein Rendezvous-Peer verfügbar")
                    await self._send_reply(writer, SOCKS5_REP_GENERAL_FAILURE)
                    writer.close()
                    return
                
                # Rendezvous-Request bauen
                client_ephemeral = os.urandom(32)
                request = await connect_to_hidden_service(
                    address=host,
                    dht=dht,
                    rendezvous_peer_id=rendezvous_peer,
                    rendezvous_address=f"127.0.0.1:{_peer_name_to_port(rendezvous_peer)}",
                    client_ephemeral_key=client_ephemeral,
                    use_network=True,
                )
                if request:
                    request.hidden_service_address = "127.0.0.1:9996"
                if request:
                    request.hidden_service_address = "127.0.0.1:9996"
                
                if request is None:
                    logger.error(f"[{conn_id}] Rendezvous-Request fehlgeschlagen (kein Descriptor?)")
                    await self._send_reply(writer, SOCKS5_REP_GENERAL_FAILURE)
                    writer.close()
                    return
                
                logger.info(f"[{conn_id}] Rendezvous-Request gebaut, sende an Intro-Point")

                # Baue einen Tunnel zum Intro-Point (erster Peer im Descriptor)
                from .hidden_service import lookup_descriptor
                descriptor = lookup_descriptor(dht, host)
                if descriptor is None or not descriptor.intro_points:
                    logger.error(f"[{conn_id}] Kein Intro-Point im Descriptor")
                    await self._send_reply(writer, SOCKS5_REP_GENERAL_FAILURE)
                    writer.close()
                    return

                intro_point = descriptor.intro_points[0]
                intro_host, intro_port = intro_point.address.split(":")
                intro_port = int(intro_port)

                from .tunnel import ErebosTunnelClient
                tunnel_client = ErebosTunnelClient(host=intro_host, port=intro_port)
                try:
                    await tunnel_client.connect()
                    logger.info(f"[{conn_id}] Tunnel zum Intro-Point {intro_point.address} aufgebaut")
                    await tunnel_client.send_rendezvous_request(request.to_dict())
                    logger.info(f"[{conn_id}] Rendezvous-Request an Intro-Point gesendet")
                    # Warte auf Antwort
                    raw = await asyncio.wait_for(tunnel_client.receive(), timeout=10.0)
                    if raw:
                        response_data = json.loads(raw.decode("utf-8"))
                        logger.info(f"[{conn_id}] Rendezvous-Antwort: {response_data}")
                        if response_data.get("status") == "ok":
                            # 2-Hop-Onion: peer3 (Intro) -> peer1 (Rendezvous)
                            # Beide Richtungen laufen ueber peer3.
                            logger.info(f"[{conn_id}] Baue 2-Hop-Onion zu peer3 (Port 9997) -> peer1 (Port 9999)")
                            from .tunnel import ErebosTunnelClient, FRAME_RELAY
                            from .onion import pack_onion_3hop
                            import json as _json
                            from pathlib import Path

                            keys_dir = Path("erebos_keys")
                            peer2_pub = (keys_dir / "peer2_x25519.pub").read_bytes()
                            peer3_pub = (keys_dir / "peer3_x25519.pub").read_bytes()
                            peer1_pub = (keys_dir / "peer1_x25519.pub").read_bytes()

                            reg_key = host[:32]
                            reg_payload = _json.dumps({"role": "client", "key": reg_key}).encode("utf-8")
                            onion = pack_onion_3hop(peer2_pub, peer3_pub, peer1_pub, reg_payload)
                            logger.info(f"[{conn_id}] Onion gebaut ({len(onion)}B)")

                            rendezvous_client = ErebosTunnelClient(host="127.0.0.1", port=9998)  # peer2
                            await rendezvous_client.connect()
                            await rendezvous_client.send_typed(FRAME_RELAY, onion)
                            logger.info(f"[{conn_id}] 3-Hop-Onion an peer2 gesendet (peer2 -> peer3 -> peer1)")

                            # Warte auf 'ready' vom Rendezvous-Punkt
                            # (Der Rendezvous-Punkt sendet 'ready', sobald beide Rollen registriert sind)
                            try:
                                while True:
                                    ready_raw = await asyncio.wait_for(rendezvous_client.receive(), timeout=60.0)
                                    if not ready_raw:
                                        break
                                    try:
                                        ready_data = json.loads(ready_raw.decode("utf-8"))
                                        logger.info(f"[{conn_id}] Rendezvous-Nachricht: {ready_data}")
                                        if ready_data.get("status") == "ready":
                                            logger.info(f"[{conn_id}] Rendezvous-Paar vollständig!")
                                            break
                                        # Ignoriere 'ok'-Bestätigungen, warte auf 'ready'
                                    except json.JSONDecodeError:
                                        logger.warning(f"[{conn_id}] Ungültige Rendezvous-Nachricht")
                            except asyncio.TimeoutError:
                                logger.warning(f"[{conn_id}] Timeout beim Warten auf 'ready'")

                            # B3: E2E-Schluesselaustausch (optional, fallback Klartext)
                            import struct as _struct
                            from .e2e import (
                                E2EClient,
                                E2E_FLAG_KEY_INIT,
                                E2E_FLAG_KEY_RESP,
                                E2E_FLAG_ENCRYPTED,
                            )
                            stream_id = conn_id & 0xFFFF
                            e2e_client = E2EClient()
                            e2e_key = None
                            try:
                                # 1) Sende E2E_KEY_INIT
                                e2e_init = e2e_client.build_key_init()
                                framed_init = _struct.pack(">H", stream_id) + bytes([E2E_FLAG_KEY_INIT]) + e2e_init
                                await rendezvous_client.send_typed(FRAME_DATA, framed_init)
                                logger.info(f"[{conn_id}] E2E_KEY_INIT gesendet (stream={stream_id})")

                                # 2) Warte auf E2E_KEY_RESP
                                for _ in range(5):
                                    resp = await asyncio.wait_for(rendezvous_client.receive(), timeout=5.0)
                                    if len(resp) < 3:
                                        continue
                                    sid = _struct.unpack(">H", resp[:2])[0]
                                    flag = resp[2]
                                    if sid == stream_id and flag == E2E_FLAG_KEY_RESP:
                                        e2e_key = e2e_client.process_key_response(resp[3:])
                                        logger.info(f"[{conn_id}] E2E-Schluessel abgeleitet (stream={stream_id})")
                                        break
                                    else:
                                        logger.debug(f"[{conn_id}] Ignoriere Frame (stream={sid}, flag={flag:#x})")
                            except Exception as e:
                                logger.warning(f"[{conn_id}] E2E-Schluesselaustausch fehlgeschlagen: {e}")

                            # 3) Sende HTTP-Anfrage (E2E-verschluesselt, falls Key vorhanden)
                            http_request = b"GET / HTTP/1.1\r\nHost: test.erebos\r\n\r\n"
                            if e2e_key is not None:
                                encrypted = e2e_client.encrypt(http_request)
                                e2e_flag = E2E_FLAG_ENCRYPTED
                                payload = encrypted
                                logger.info(f"[{conn_id}] HTTP-Anfrage E2E-verschluesselt (stream={stream_id})")
                            else:
                                e2e_flag = 0x00
                                payload = http_request
                            framed_request = _struct.pack(">H", stream_id) + bytes([e2e_flag]) + payload
                            await rendezvous_client.send_typed(FRAME_DATA, framed_request)
                            logger.info(f"[{conn_id}] HTTP-Anfrage über Rendezvous-Tunnel gesendet (stream={stream_id}, e2e_flag={e2e_flag:#x})")

                            # Warte auf Antwort vom Hidden Service
                            # (Die erste Antwort kann die Registrierungs-Bestätigung sein)
                            http_response = None
                            for _ in range(3):
                                try:
                                    resp = await asyncio.wait_for(rendezvous_client.receive(), timeout=5.0)
                                    if resp:
                                        # Rendezvous-Pfad: resp = [stream_id:2B][e2e_flag:1B][nutzdaten]
                                        if len(resp) < 3:
                                            logger.debug(f"[{conn_id}] Ignoriere zu kurzen Frame: {resp[:16]!r}...")
                                            continue
                                        import struct as _struct
                                        resp_stream_id = _struct.unpack(">H", resp[:2])[0]
                                        resp_e2e_flag = resp[2]
                                        resp_payload = resp[3:]
                                        # Nur Antworten fuer die EIGENE Stream-ID akzeptieren
                                        if resp_stream_id != stream_id:
                                            logger.debug(
                                                f"[{conn_id}] Ignoriere Frame fuer fremden Stream "
                                                f"(stream={resp_stream_id}, erwartet={stream_id})"
                                            )
                                            continue
                                        # B3: E2E-entschluesseln, falls verschluesselt
                                        if resp_e2e_flag == E2E_FLAG_ENCRYPTED and e2e_key is not None:
                                            try:
                                                resp_payload = e2e_client.decrypt(resp_payload)
                                                logger.info(f"[{conn_id}] E2E-Antwort entschluesselt (stream={stream_id})")
                                            except Exception as e:
                                                logger.error(f"[{conn_id}] E2E-Entschluesselung fehlgeschlagen: {e}")
                                                continue
                                        elif resp_e2e_flag != 0x00:
                                            logger.debug(f"[{conn_id}] Unbekanntes e2e_flag: {resp_e2e_flag:#x}")
                                        if resp_payload.startswith(b"HTTP/"):
                                            http_response = resp_payload
                                            break
                                        else:
                                            logger.debug(f"[{conn_id}] Ignoriere Frame (stream={resp_stream_id}): {resp_payload[:16]!r}...")
                                except asyncio.TimeoutError:
                                    break
                            if http_response:
                                logger.info(f"[{conn_id}] HTTP-Antwort vom Hidden Service: {len(http_response)}B")
                                # SOCKS5-Reply senden (Protokoll-Abschluss des CONNECT)
                                await self._send_reply(writer, SOCKS5_REP_SUCCESS)
                                # WICHTIG: Die eigentliche HTTP-Antwort an curl weiterreichen!
                                # Ohne diese Zeilen bekommt curl nur die SOCKS5-Reply und
                                # bricht mit "Empty reply from server" ab.
                                try:
                                    writer.write(http_response)
                                    await writer.drain()
                                    logger.info(f"[{conn_id}] HTTP-Antwort an Client weitergeleitet ({len(http_response)}B)")
                                except Exception as e:
                                    logger.error(f"[{conn_id}] Fehler beim Senden der HTTP-Antwort an Client: {e}")
                            else:
                                logger.error(f"[{conn_id}] Keine HTTP-Antwort vom Hidden Service")
                                await self._send_reply(writer, SOCKS5_REP_GENERAL_FAILURE)

                            await rendezvous_client.close()
                        else:
                            await self._send_reply(writer, SOCKS5_REP_GENERAL_FAILURE)
                    else:
                        logger.error(f"[{conn_id}] Keine Antwort vom Intro-Point")
                        await self._send_reply(writer, SOCKS5_REP_GENERAL_FAILURE)
                except Exception as e:
                    logger.error(f"[{conn_id}] Fehler bei Rendezvous-Kommunikation: {e}")
                    await self._send_reply(writer, SOCKS5_REP_GENERAL_FAILURE)
                finally:
                    await tunnel_client.close()
                writer.close()
                return

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
            # Cover-Traffic-Injector (P1.1b): sendet FRAME_COVER-Frames
            # im Burst-Modus, um Timing-Fingerprinting zu verwischen.
            # Die Werte kommen aus CoverConfig.for_profile() -- kalibriert
            # aus echten HTTP-Burst-Daten (v0.4.2/v0.4.4).
            profile = getattr(self, "_cover_profile", None) or "web"
            cover_config = CoverConfig.for_profile(profile)
            cover_config.adaptive = True
            cover_config.reactive = True
            cover = TunnelCoverInjector(
                tunnel,
                cover_config,
                anonymity_provider=self._anonymity_provider,
                auto_profile=getattr(self, "_auto_profile", False),
                detector=getattr(self, "_profile_detector", None),
            )
            await cover.start()

            async def tunnel_to_client():
                while True:
                    data = await tunnel.receive()
                    if not data:
                        break
                    writer.write(data)
                    await writer.drain()
                    # Reactive Drop-Cover: Downlink-Burst melden
                    if cover is not None:
                        cover.notify_downlink(len(data))

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
                    await tunnel.send_typed(FRAME_DATA, data)
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
